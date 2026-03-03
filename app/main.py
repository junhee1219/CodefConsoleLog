import logging
from datetime import datetime, timedelta

from fastapi import FastAPI, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, extract
from sqlalchemy.orm import Session

from app.config import COLLECT_INTERVAL_MINUTES
from app.database import engine, get_db, Base
from app.models import ErrReport
from app.org_codes import ORGANIZATION_MAP, get_org_name

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Codef Error Report Viewer")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    # 백그라운드 스케줄러
    from apscheduler.schedulers.background import BackgroundScheduler
    from app.collector import collect_today

    scheduler = BackgroundScheduler()
    scheduler.add_job(collect_today, "interval", minutes=COLLECT_INTERVAL_MINUTES, next_run_time=datetime.now())
    scheduler.start()


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    err_code: str = Query("", alias="err_code"),
    product_name: str = Query("", alias="product_name"),
    business_type: str = Query("", alias="business_type"),
    keyword: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    hour_from: str = Query("", alias="hour_from"),
    hour_to: str = Query("", alias="hour_to"),
):
    q = db.query(ErrReport)

    if err_code:
        q = q.filter(ErrReport.err_code == err_code)
    if product_name:
        q = q.filter(ErrReport.product_name == product_name)
    if business_type:
        q = q.filter(ErrReport.business_type == business_type)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            (ErrReport.err_msg.like(like))
            | (ErrReport.detail_extra_message.like(like))
            | (ErrReport.mid.like(like))
            | (ErrReport.detail_organization.like(like))
        )
    if date_from:
        try:
            q = q.filter(ErrReport.reg_time >= datetime.strptime(date_from, "%Y-%m-%d"))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(ErrReport.reg_time < datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))
        except ValueError:
            pass
    if hour_from:
        try:
            q = q.filter(extract("hour", ErrReport.reg_time) >= int(hour_from))
        except ValueError:
            pass
    if hour_to:
        try:
            q = q.filter(extract("hour", ErrReport.reg_time) <= int(hour_to))
        except ValueError:
            pass

    total = q.count()
    reports = q.order_by(ErrReport.reg_time.desc()).offset((page - 1) * size).limit(size).all()
    total_pages = (total + size - 1) // size

    # 필터 옵션용 distinct 값
    err_codes = [r[0] for r in db.query(ErrReport.err_code).distinct().order_by(ErrReport.err_code).all() if r[0]]
    product_names = [r[0] for r in db.query(ErrReport.product_name).distinct().order_by(ErrReport.product_name).all() if r[0]]
    biz_type_rows = db.query(ErrReport.business_type, ErrReport.business_type_name).distinct().order_by(ErrReport.business_type).all()
    business_types = [(r[0], r[1] or r[0]) for r in biz_type_rows if r[0]]

    return templates.TemplateResponse("list.html", {
        "request": request,
        "reports": reports,
        "page": page,
        "size": size,
        "total": total,
        "total_pages": total_pages,
        "err_code": err_code,
        "product_name": product_name,
        "business_type": business_type,
        "keyword": keyword,
        "date_from": date_from,
        "date_to": date_to,
        "hour_from": hour_from,
        "hour_to": hour_to,
        "err_codes": err_codes,
        "product_names": product_names,
        "business_types": business_types,
        "get_org_name": get_org_name,
    })


@app.get("/detail/{mid}", response_class=HTMLResponse)
def detail(request: Request, mid: str, db: Session = Depends(get_db)):
    import json as _json
    report = db.query(ErrReport).filter(ErrReport.mid == mid).first()
    cr = {}
    detail_parsed = {}
    if report and report.detail_raw:
        try:
            detail_parsed = _json.loads(report.detail_raw)
            cr = detail_parsed.get("cr", {})
        except _json.JSONDecodeError:
            pass
    detail_json_pretty = _json.dumps(detail_parsed, indent=2, ensure_ascii=False) if detail_parsed else ""
    return templates.TemplateResponse("detail.html", {
        "request": request,
        "report": report,
        "cr": cr,
        "detail_parsed": detail_parsed,
        "detail_json_pretty": detail_json_pretty,
        "get_org_name": get_org_name,
    })


@app.get("/stats", response_class=HTMLResponse)
def stats(
    request: Request,
    db: Session = Depends(get_db),
    date_from: str = Query("", alias="date_from"),
    date_to: str = Query("", alias="date_to"),
):
    import json as _json
    today = datetime.now().strftime("%Y-%m-%d")
    if not date_from:
        date_from = today
    if not date_to:
        date_to = date_from

    try:
        dt = datetime.strptime(date_from, "%Y-%m-%d")
    except ValueError:
        dt = datetime.now()
        date_from = dt.strftime("%Y-%m-%d")

    try:
        dt_end = datetime.strptime(date_to, "%Y-%m-%d")
    except ValueError:
        dt_end = dt
        date_to = dt_end.strftime("%Y-%m-%d")

    dt_next = dt_end + timedelta(days=1)
    date_filter = [ErrReport.reg_time >= dt, ErrReport.reg_time < dt_next]

    total = db.query(ErrReport).filter(*date_filter).count()

    # 에러코드별 집계
    by_err_code = (
        db.query(ErrReport.err_code, func.count(ErrReport.id))
        .filter(*date_filter)
        .group_by(ErrReport.err_code)
        .order_by(func.count(ErrReport.id).desc())
        .all()
    )

    # 기관별 집계 (detail_organization)
    by_org = (
        db.query(ErrReport.detail_organization, func.count(ErrReport.id))
        .filter(*date_filter)
        .group_by(ErrReport.detail_organization)
        .order_by(func.count(ErrReport.id).desc())
        .all()
    )

    # 상품명별 집계
    by_product = (
        db.query(ErrReport.product_name, func.count(ErrReport.id))
        .filter(*date_filter)
        .group_by(ErrReport.product_name)
        .order_by(func.count(ErrReport.id).desc())
        .all()
    )

    # 기관분류별 집계
    by_biz = (
        db.query(ErrReport.business_type, ErrReport.business_type_name, func.count(ErrReport.id))
        .filter(*date_filter)
        .group_by(ErrReport.business_type, ErrReport.business_type_name)
        .order_by(func.count(ErrReport.id).desc())
        .all()
    )

    # 에러코드 → 에러메시지 매핑
    err_msg_rows = (
        db.query(ErrReport.err_code, ErrReport.err_msg)
        .filter(*date_filter, ErrReport.err_code.isnot(None))
        .group_by(ErrReport.err_code, ErrReport.err_msg)
        .all()
    )
    err_code_msg_map = {r[0]: r[1] for r in err_msg_rows if r[0]}

    # 에러코드별 기관 내역
    err_code_org_rows = (
        db.query(ErrReport.err_code, ErrReport.detail_organization, func.count(ErrReport.id))
        .filter(*date_filter)
        .group_by(ErrReport.err_code, ErrReport.detail_organization)
        .order_by(ErrReport.err_code, func.count(ErrReport.id).desc())
        .all()
    )
    # {err_code: [(org, cnt), ...]}
    err_code_org_map: dict[str, list] = {}
    err_code_totals: dict[str, int] = {}
    for code, org, cnt in err_code_org_rows:
        err_code_org_map.setdefault(code, []).append((org, cnt))
        err_code_totals[code] = err_code_totals.get(code, 0) + cnt
    # 에러코드를 총 건수 desc로 정렬
    sorted_err_codes = sorted(err_code_totals.keys(), key=lambda c: -err_code_totals[c])

    return templates.TemplateResponse("stats.html", {
        "request": request,
        "date_from": date_from,
        "date_to": date_to,
        "total": total,
        "by_err_code": by_err_code,
        "by_org": by_org,
        "by_product": by_product,
        "by_biz": by_biz,
        "err_code_org_map": err_code_org_map,
        "err_code_totals": err_code_totals,
        "sorted_err_codes": sorted_err_codes,
        "err_code_msg_map": err_code_msg_map,
        "get_org_name": get_org_name,
    })


@app.post("/collect")
def trigger_collect(date: str = Query(..., description="YYYYMMDD")):
    """수동 수집 트리거 (단일 날짜)"""
    from app.collector import collect_date
    import threading
    threading.Thread(target=collect_date, args=(date,), daemon=True).start()
    return {"status": "started", "date": date}


@app.post("/collect-range")
def trigger_collect_range(start: str = Query(..., description="YYYYMMDD"), end: str = Query(..., description="YYYYMMDD")):
    """수동 수집 트리거 (날짜 범위)"""
    from app.collector import collect_date_range
    import threading
    threading.Thread(target=collect_date_range, args=(start, end), daemon=True).start()
    return {"status": "started", "start": start, "end": end}
