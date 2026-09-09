# DB 마이그레이션

Flyway가 스키마 변경을 관리하고 Hibernate는 `ddl-auto=validate`로 엔티티와 DB 구조를 검사합니다.
초기 버전은 `src/main/resources/db/migration/V1__create_initial_schema.sql`입니다.

## 새 DB

기존 실행 명령을 그대로 사용합니다.

```bash
docker compose up -d --wait
bash gradlew bootRun
```

빈 DB에는 V1 SQL이 실행되어 업무 테이블 3개와 Flyway의 `flyway_schema_history`가 생성됩니다.
재시작 때는 완료된 버전을 다시 실행하지 않습니다.

## 기존 Hibernate DB의 최초 전환

이 절차는 **현재 V1과 컬럼/인덱스가 일치하는 기존 DB**에만 적용합니다.
오래된 버전의 일부 테이블만 있는 DB에는 먼저 별도의 업그레이드 SQL이 필요합니다.
`baseline`은 누락된 테이블이나 컬럼을 보충하지 않습니다.

1. 백엔드와 DB에 쓰는 다른 클라이언트를 중지합니다.
2. DB를 백업합니다. 백업 파일은 Git에 커밋하지 않습니다.
3. V1을 적용한 별도 빈 DB와 기존 DB의 컬럼 타입·NULL 허용·기본값·인덱스를 비교합니다.
4. 일치할 때만 다음 명령으로 한 번 실행합니다.

```bash
SPRING_FLYWAY_BASELINE_ON_MIGRATE=true bash gradlew bootRun
```

기존 구조를 버전 1(BASELINE)로 등록하며 V1의 CREATE 문은 실행하지 않습니다.
따라서 기존 데이터는 유지됩니다. BASELINE 등록은 기존 V1 SQL의 체크섬 검증을 대신하지 않으므로
전환 전 구조 비교가 필요합니다.

등록 후 서버를 종료하고 **일반 명령으로 다시 실행**합니다.

```bash
bash gradlew bootRun
```

`baseline-on-migrate=true`를 application.properties나 영구 환경 변수에 저장하지 마세요.
일반 설정에서는 이력이 없는 비어 있지 않은 DB에 자동으로 버전을 붙이지 않고 기동에 실패합니다.

## 이후 변경 규칙

- 적용된 V1 파일은 수정하지 않습니다. 다음 변경은 `V2__설명.sql`, 그다음은 `V3__설명.sql`로 추가합니다.
- 엔티티 변경과 대응 SQL을 같은 변경에 포함합니다.
- `instantType`/`jsonTextType`은 MySQL에서 `DATETIME(6)`/`LONGTEXT`입니다. H2 테스트에서만 `TIMESTAMP(6) WITH TIME ZONE`/`CLOB`을 사용합니다.
- 이미 적용된 환경의 SQL 및 타입 placeholder 값을 변경하지 않습니다. 테스트와 실제 MySQL의 타입 차이를 보완하기 위한 설정입니다.
- 테스트도 Hibernate 자동 생성이 아니라 동일한 Flyway SQL을 실행한 뒤 엔티티 검증을 수행합니다.
- 실행된 SQL의 체크섬 불일치는 기동 실패로 처리합니다. 원인 확인 없이 history 수정이나 repair로 우회하지 않습니다.
- `clean-disabled=true`로 Flyway의 전체 스키마 삭제 기능을 막았습니다.
- MySQL DDL은 실패 시 전체가 자동 롤백된다고 가정할 수 없습니다. 스키마 변경 전 백업 및 별도 DB 검증을 유지합니다.

## 전환 검증 기록 (2026-09-07)

- 백업: `reports/backups/before-flyway-20260907-183648.sql` (로컬 전용).
- 기존 업무 데이터: risk_events 4건, processed_frames 7건, stream_completions 1건.
- 별도 빈 MySQL DB에서 V1 적용 및 Hibernate validate 통과.
- 기존 DB와 신규 DB의 컬럼 타입/NULL/기본값/collation/인덱스 비교 일치.
- 기존 DB는 버전 1로 BASELINE 등록. 일반 설정 재시작 및 데이터 덤프 동일성 검증 수행.
- 백엔드 테스트 30개: 신규 DB 초기화, 재실행, 자동 baseline 거부, 명시적 baseline 데이터 보존, 체크섬 변경 거부, clean 차단 및 기존 API 테스트 포함.

## 참고

- [Spring Boot 데이터베이스 초기화](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
- [Flyway baseline-on-migrate](https://documentation.red-gate.com/flyway/reference/configuration/flyway-namespace/flyway-baseline-on-migrate-setting)
