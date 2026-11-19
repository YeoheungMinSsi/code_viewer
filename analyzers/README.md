# 언어별 분석기

현재 Python 호출·구조 분석과 Java 8 구조 분석을 지원합니다. Java 분석에는 requirements.txt 설치가 필요합니다. 새 언어는 독립 모듈에 outline(raw: bytes) -> str 함수를 구현하고 ANALYZERS에 확장자, 언어 ID, 표시 이름과 분석 함수를 등록합니다. UI는 /languages에서 지원 형식을 읽습니다.

공통 출력은 section 아래 details/summary로 구성합니다. 종류는 cls, fn, var, imp, entry 클래스이며 data-line은 선언 줄 번호, data-name은 검색 이름입니다. 본문은 pre, 줄 번호는 i 태그입니다. 원문과 이름은 반드시 HTML 이스케이프합니다. 소스를 실행하지 않습니다.

호출 버튼은 call 클래스와 data-target 속성을 사용합니다. 내부 대상은 선언 줄, 미확정은 ?설명, 외부 대상은 모듈|이름입니다. 잘못된 소스는 SyntaxError 또는 ValueError로 알립니다.

현재 파일 간 모듈 경로 해석은 Python 규칙이므로 새 언어의 외부 호출을 지원할 때 해당 언어 규칙도 추가해야 합니다. 렌더링과 캔버스 조작은 재사용합니다.
