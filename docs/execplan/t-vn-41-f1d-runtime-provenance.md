# T-VN-41-F1D-C1b PinVi seven-image provenance 실행 계획

## 목표

F1D candidate가 PinVi API·Web·Dagster 세 image를 하나의 exact source revision으로
검증할 수 있게 한다. image tag나 실행 중 container는 provenance의 정본이 아니다.

## 설계

각 final Docker stage는 `PINVI_SOURCE_REVISION`과 `PINVI_BUILD_ENVIRONMENT`를 build
argument로 받고, production/staging에서는 소문자 40자리 commit만 수용한다. 최종 image에
`org.opencontainers.image.revision`과 `io.pinvi.build.environment` label을 기록한다.
이 검증은 Dockerfile 내부에서 수행하므로 Manager가 주입한 candidate build argument가 누락되거나
잘못된 경우 image 생성 자체가 실패한다.

Manager Compose는 세 PinVi service 모두에 같은 두 argument를 명시하고, source 계약 테스트는
세 build mapping과 image label을 함께 확인한다. PinVi merge SHA를 새 Manager release pinset에
원자 갱신한 뒤 n150 F1D rebuild를 다시 실행한다.

## 완료 기준

- [ ] API·Web·Dagster final image가 동일한 OCI revision/environment label을 가진다.
- [ ] production/staging의 비정상 revision이 각 image build에서 거부된다.
- [ ] PinVi 및 Manager 계약 테스트가 세 service argument를 확인한다.
- [ ] 새 PinVi merge SHA로 Manager pinset을 갱신하고 n150 candidate preflight를 통과한다.
