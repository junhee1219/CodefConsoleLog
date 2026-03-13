# Codef Error Report Viewer

Codef API의 에러 리포트를 주기적으로 수집하고 웹에서 조회하는 시스템입니다.

## 요구사항

- Python 3.13+
- MySQL (Docker 컨테이너 `mysql2`, 포트 3307)

## 설정

프로젝트 루트에 `.env` 파일을 생성합니다.

```env
DB_HOST=127.0.0.1
DB_PORT=3307
DB_USER=app
DB_PASS=app1234
DB_NAME=codef_err_log

CODEF_LOGIN_EMAIL=<암호화된 이메일>
CODEF_LOGIN_PASSWORD=<암호화된 비밀번호>
CODEF_LOGIN_IV=<IV 값>

SLACK_WEBHOOK_URL=<Slack Webhook URL>

COLLECT_INTERVAL=5
```

## 실행 방법

### 1. DB 설정

Docker MySQL 컨테이너가 없다면 먼저 생성합니다.

```bash
docker run -d --name mysql2 -p 3307:3306 -e MYSQL_ROOT_PASSWORD=root mysql:8
```

컨테이너에 접속하여 DB와 유저를 생성합니다.

```bash
docker exec -it mysql2 mysql -uroot -proot
```

```sql
CREATE DATABASE codef_err_log CHARACTER SET utf8mb4;
CREATE USER 'app'@'%' IDENTIFIED BY 'app1234';
GRANT ALL PRIVILEGES ON codef_err_log.* TO 'app'@'%';
FLUSH PRIVILEGES;
```

이후에는 컨테이너 시작만 하면 됩니다.

```bash
docker start mysql2
```

테이블은 서버 시작 시 자동 생성됩니다.

### 2. 의존성 설치

```bash
pip install -r requirements.txt
```

### 3. 서버 실행

```bash
# 방법 1: run.sh 사용 (기본 포트 1717)
./run.sh

# 방법 2: 직접 실행
uvicorn app.main:app --host 0.0.0.0 --port 1717 --reload
```

서버가 시작되면 http://localhost:1717 에서 접속할 수 있습니다.

에러 리포트는 `COLLECT_INTERVAL` (기본 5분) 간격으로 자동 수집됩니다.

## 팀원 접속 안내

같은 네트워크(사내 Wi-Fi 등)에 있는 팀원들이 접속할 수 있습니다.

### 내 IP 확인

```bash
# macOS
ipconfig getifaddr en0

# Windows
ipconfig | findstr IPv4

# Linux
hostname -I
```

### 서버 실행 후 슬랙에 공유할 메시지 예시

```
에러 리포트 뷰어 띄웠습니다.
접속 주소: http://<내 IP>:<포트>
(예: http://192.168.0.10:1717)
같은 Wi-Fi에서 접속 가능합니다.
```

> 포트는 `run.sh` 실행 시 인자로 변경 가능합니다. (예: `./run.sh 8080`)
