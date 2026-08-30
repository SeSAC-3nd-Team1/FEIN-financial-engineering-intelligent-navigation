# Infrastructure

프로젝트의 클라우드 인프라, 배포 및 보안 관련 작업을 관리합니다.

## 주요 작업

- Azure 인프라
- CI/CD
- Container 배포
- 네트워크
- 접근 권한
- Secret 관리
- 모니터링
- 보안 설정

## Azure 데이터 Storage

Issue #16에서 기존 RG `project-3rd-team-1` / Korea Central에 `stfeindata`를 구성한다. [data-storage.bicep](data-storage.bicep)은 StorageV2, Standard_LRS, HTTPS/TLS 1.2, shared key/anonymous access 차단과 `raw`, `processed`, `features` private container를 재현한다.

```bash
az deployment group create \
  --resource-group project-3rd-team-1 \
  --template-file infra/data-storage.bicep
```

애플리케이션 실행 identity에는 Storage Account scope의 `Storage Blob Data Contributor`만 부여한다. 현재 개발자 계정 예시는 다음과 같으며 object ID는 환경별로 조회해 넣는다.

```bash
az role assignment create \
  --assignee-object-id <principal-object-id> \
  --assignee-principal-type User \
  --role "Storage Blob Data Contributor" \
  --scope "$(az storage account show -g project-3rd-team-1 -n stfeindata --query id -o tsv)"
```

운영 workload가 추가되면 system/user assigned Managed Identity를 먼저 만들고 같은 최소 역할을 부여한다. Account Key/SAS/connection string은 Key Vault나 repository에 새로 저장하지 않는다.
