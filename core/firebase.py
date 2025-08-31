import firebase_admin
from firebase_admin import credentials
from pathlib import Path


def setup_firebase():
    # 다운로드한 Firebase 비공개 키 파일의 경로를 입력하세요.
    # 이 파일은 프로젝트 루트나 안전한 곳에 보관해야 합니다.
    BASE_DIR = Path(__file__).resolve().parent.parent
    cred_path = BASE_DIR/"firebase-secret-key.json"

    if not cred_path.is_file():
        # 파일이 없으면 에러 메시지를 명확하게 보여주고 중단합니다.
        raise FileNotFoundError(
            f"Firebase 인증 키 파일을 찾을 수 없습니다. 경로를 확인하세요: {cred_path}"
        )
    
    try:
        # 이미 초기화되었는지 확인하여 중복 초기화를 방지합니다.
        firebase_admin.get_app()
    except ValueError:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    print("🔥 Firebase Admin SDK가 성공적으로 초기화되었습니다.")