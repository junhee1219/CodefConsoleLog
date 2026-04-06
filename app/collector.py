import json
import logging
from datetime import datetime

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import CODEF_BASE_URL, CODEF_LOGIN_PAYLOAD, SLACK_WEBHOOK_URL
from app.org_codes import get_org_name
from app.database import SessionLocal
from app.models import ErrReport

logger = logging.getLogger(__name__)

BIZ_TYPE_NAME_MAP = {
    "PB": "세금계산서",
}

HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://codef.io",
    "Referer": "https://codef.io/login",
}


def login(client: httpx.Client) -> str:
    resp = client.post(
        f"{CODEF_BASE_URL}/auth/login",
        json=CODEF_LOGIN_PAYLOAD,
        headers=HEADERS,
    )
    resp.raise_for_status()
    token = resp.headers.get("Authorization")
    if not token:
        raise RuntimeError("로그인 실패: Authorization 헤더 없음")
    return token


def fetch_list(client: httpx.Client, token: str, date: str) -> dict:
    payload = {
        "startNo": 0,
        "length": 0,
        "pageSize": 99999,
        "pageIndex": 0,
        "pageSizeOptions": [5, 10, 25, 100],
        "errCodeInfo": {},
        "serviceType": "0",
        "serializedDate": datetime.now().strftime("%Y%m%d"),
        "date": date,
    }
    resp = client.post(
        f"{CODEF_BASE_URL}/errReport/searchErrReportByConditions",
        json=payload,
        headers={**HEADERS, "Authorization": token},
    )
    resp.raise_for_status()
    return resp.json()


def fetch_detail(client: httpx.Client, token: str, mid: str) -> dict | None:
    resp = client.post(
        f"{CODEF_BASE_URL}/errReport/getErrDetail",
        json={"mid": mid},
        headers={**HEADERS, "Authorization": token},
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("result") != "SUCCESS":
        return None
    raw_value = data.get("resultJson", {}).get("value")
    if not raw_value:
        return None
    return json.loads(raw_value)


def parse_reg_time(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def send_slack(new_reports: list[dict], date: str = ""):
    """신규 에러가 있을 때 Slack 웹훅으로 알림을 보낸다."""
    if not SLACK_WEBHOOK_URL or not new_reports:
        return
    try:
        # 에러코드별 집계
        code_counts: dict[str, int] = {}
        org_counts: dict[str, int] = {}
        for r in new_reports:
            code = r.get("err_code", "UNKNOWN")
            code_counts[code] = code_counts.get(code, 0) + 1
            org = r.get("organization", "")
            org_name = get_org_name(org) if org else "미분류"
            org_counts[org_name] = org_counts.get(org_name, 0) + 1

        date_display = f"{date[:4]}-{date[4:6]}-{date[6:]}" if len(date) == 8 else date
        code_lines = "\n".join(f"  • `{c}` : {n}건" for c, n in sorted(code_counts.items(), key=lambda x: -x[1]))
        org_lines = "\n".join(f"  • {o} : {n}건" for o, n in sorted(org_counts.items(), key=lambda x: -x[1]))

        text = (
            f":rotating_light: *[{date_display}] Codef 신규 에러 {len(new_reports)}건 수집*\n\n"
            f"*에러코드별*\n{code_lines}\n\n"
            f"*기관별*\n{org_lines}"
        )

        httpx.post(SLACK_WEBHOOK_URL, json={"text": text}, timeout=10)
    except Exception as e:
        logger.warning(f"Slack 알림 실패: {e}")


def collect_date(date: str):
    """주어진 날짜(YYYYMMDD)의 에러 리포트를 수집한다."""
    logger.info(f"수집 시작: {date}")
    client = httpx.Client(timeout=30)
    try:
        token = login(client)
        logger.info("로그인 성공")

        result = fetch_list(client, token, date)
        rj = result.get("resultJson", {})
        err_list = rj.get("errList", [])
        total_new = 0
        new_reports = []

        if err_list:
            db: Session = SessionLocal()
            try:
                for item in err_list:
                    mid = item.get("mid")
                    if not mid:
                        continue
                    exists = db.query(ErrReport.id).filter(ErrReport.mid == mid).first()
                    if exists:
                        continue

                    detail = fetch_detail(client, token, mid)

                    report = ErrReport(
                        mid=mid,
                        log_id=item.get("logId"),
                        reg_time=parse_reg_time(item.get("regTime")),
                        product_code=item.get("productCode"),
                        product_name=item.get("productName"),
                        business_type=item.get("businessType"),
                        business_type_name=BIZ_TYPE_NAME_MAP.get(item.get("businessType"), item.get("businessTypeName")),
                        product_info2=item.get("productInfo2"),
                        product_info3=item.get("productInfo3"),
                        err_type=item.get("errType"),
                        err_code=item.get("errCode"),
                        err_msg=item.get("errMsg"),
                        detail_raw=json.dumps(detail, ensure_ascii=False) if detail else None,
                        detail_extra_message=detail.get("result", {}).get("extraMessage") if detail else None,
                        detail_organization=detail.get("cr", {}).get("organization") if detail else None,
                        detail_connected_id=detail.get("cr", {}).get("connectedId") if detail else None,
                        detail_err_cnt=detail.get("summary", {}).get("errCnt") if detail else None,
                        detail_success_cnt=detail.get("summary", {}).get("successCnt") if detail else None,
                        detail_req_cnt=detail.get("summary", {}).get("reqCnt") if detail else None,
                    )
                    db.add(report)
                    total_new += 1
                    new_reports.append({
                        "err_code": item.get("errCode"),
                        "organization": detail.get("cr", {}).get("organization") if detail else "",
                    })
                db.commit()
            finally:
                db.close()

        logger.info(f"수집 완료: {date} / 신규 {total_new}건 (API 총 {len(err_list)}건)")

        if new_reports:
            send_slack(new_reports, date)
    finally:
        client.close()


def _login_with_retry(client: httpx.Client, retries: int = 3, delay: float = 5.0) -> str:
    import time
    for attempt in range(retries):
        try:
            return login(client)
        except Exception:
            if attempt == retries - 1:
                raise
            logger.warning(f"로그인 실패, {delay}초 후 재시도 ({attempt + 1}/{retries})")
            time.sleep(delay)


def collect_date_range(start_date: str, end_date: str):
    """start_date ~ end_date (YYYYMMDD) 범위를 한 세션으로 수집한다."""
    import time
    from datetime import timedelta
    logger.info(f"일괄 수집 시작: {start_date} ~ {end_date}")
    client = httpx.Client(timeout=30)
    try:
        token = _login_with_retry(client)
        logger.info("로그인 성공")

        current = datetime.strptime(start_date, "%Y%m%d")
        end = datetime.strptime(end_date, "%Y%m%d")
        total_all = 0

        while current <= end:
            date_str = current.strftime("%Y%m%d")
            try:
                try:
                    result = fetch_list(client, token, date_str)
                except httpx.HTTPStatusError:
                    time.sleep(3)
                    token = _login_with_retry(client)
                    result = fetch_list(client, token, date_str)

                rj = result.get("resultJson", {})
                err_list = rj.get("errList", [])
                total_new = 0
                new_reports = []

                if err_list:
                    db: Session = SessionLocal()
                    try:
                        for item in err_list:
                            mid = item.get("mid")
                            if not mid:
                                continue
                            exists = db.query(ErrReport.id).filter(ErrReport.mid == mid).first()
                            if exists:
                                continue

                            try:
                                detail = fetch_detail(client, token, mid)
                            except httpx.HTTPStatusError:
                                try:
                                    time.sleep(2)
                                    token = _login_with_retry(client)
                                    detail = fetch_detail(client, token, mid)
                                except Exception:
                                    logger.warning(f"  {mid} detail 수집 실패, 스킵")
                                    detail = None

                            report = ErrReport(
                                mid=mid,
                                log_id=item.get("logId"),
                                reg_time=parse_reg_time(item.get("regTime")),
                                product_code=item.get("productCode"),
                                product_name=item.get("productName"),
                                business_type=item.get("businessType"),
                                business_type_name=BIZ_TYPE_NAME_MAP.get(item.get("businessType"), item.get("businessTypeName")),
                                product_info2=item.get("productInfo2"),
                                product_info3=item.get("productInfo3"),
                                err_type=item.get("errType"),
                                err_code=item.get("errCode"),
                                err_msg=item.get("errMsg"),
                                detail_raw=json.dumps(detail, ensure_ascii=False) if detail else None,
                                detail_extra_message=detail.get("result", {}).get("extraMessage") if detail else None,
                                detail_organization=detail.get("cr", {}).get("organization") if detail else None,
                                detail_connected_id=detail.get("cr", {}).get("connectedId") if detail else None,
                                detail_err_cnt=detail.get("summary", {}).get("errCnt") if detail else None,
                                detail_success_cnt=detail.get("summary", {}).get("successCnt") if detail else None,
                                detail_req_cnt=detail.get("summary", {}).get("reqCnt") if detail else None,
                            )
                            db.add(report)
                            total_new += 1
                            new_reports.append({
                                "err_code": item.get("errCode"),
                                "organization": detail.get("cr", {}).get("organization") if detail else "",
                            })
                        db.commit()
                    finally:
                        db.close()

                total_all += total_new
                logger.info(f"  {date_str} 완료: 신규 {total_new}건")
                if new_reports:
                    send_slack(new_reports, date_str)
            except Exception as e:
                logger.error(f"  {date_str} 수집 실패, 다음 날짜로 넘어감: {e}")

            current += timedelta(days=1)
            time.sleep(1)

        logger.info(f"일괄 수집 완료: {start_date}~{end_date} / 총 신규 {total_all}건")
    finally:
        client.close()


def collect_today():
    """오늘 날짜 수집. DB에 마지막 수집일이 오늘 이전이면 빠진 날짜도 함께 수집."""
    from datetime import timedelta
    today = datetime.now().strftime("%Y%m%d")

    db: Session = SessionLocal()
    try:
        last = db.query(func.max(ErrReport.reg_time)).scalar()
    finally:
        db.close()

    if last:
        last_date = (last + timedelta(days=1)).strftime("%Y%m%d")
        if last_date < today:
            logger.info(f"빠진 날짜 보충 수집: {last_date} ~ {today}")
            collect_date_range(last_date, today)
            return

    collect_date(today)
