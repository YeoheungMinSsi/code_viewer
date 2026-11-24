# 언어별 분석기

현재 Python 호출·구조 분석과 Java 8 구조·같은 파일 호출·상속·기본 오버로딩 분석을 지원합니다. Java 분석에는 requirements.txt 설치가 필요합니다. 새 언어는 독립 모듈에 outline(raw: bytes) -> str 함수를 구현하고 ANALYZERS에 확장자, 언어 ID, 표시 이름과 분석 함수를 등록합니다. UI는 /languages에서 지원 형식을 읽습니다.

공통 출력은 section 아래 details/summary로 구성합니다. 종류는 cls, fn, var, imp, entry 클래스이며 data-line은 파일 안에서 고유한 선언 식별자(Python은 줄 번호, Java는 J줄_열), data-name은 검색 이름입니다. 본문은 pre, 줄 번호는 i 태그입니다. 원문과 이름은 반드시 HTML 이스케이프합니다. 소스를 실행하지 않습니다.

호출 버튼은 call 클래스와 data-target 속성을 사용합니다. 내부 대상은 해당 선언의 data-line 값, 미확정은 ?설명, 외부 대상은 모듈|이름입니다. 잘못된 소스는 SyntaxError 또는 ValueError로 알립니다.

Python 외부 호출은 모듈 경로로 해석합니다. C#은 csharp_calls.Project에서 불러온 소스 묶음을 분석하고 /csharp-links가 파일별 호출 정보를 반환합니다. data-cs-call은 UTF-8 바이트 위치 식별자이며, 갱신된 data-target은 @cs: 뒤에 [파일 경로, 선언 식별자] JSON을 담습니다. 같은 경로가 중복되거나 분석 결과가 오래되면 연결하지 않습니다. 렌더링과 캔버스 조작은 재사용합니다.

C# 고급 해석은 csharp_advanced.py의 순수 분석 함수에서 확장 메서드 가시성·제네릭 제약·안정적인 지역 변수 초기화·typeof/GetMethod/Invoke를 처리합니다. 호출 식별자는 시작/종료 UTF-8 바이트 위치를 포함해 중첩 호출 충돌을 막고, 선언 식별자는 기존 시작 위치를 유지합니다. 런타임 대상은 추정 연결하지 않습니다.
