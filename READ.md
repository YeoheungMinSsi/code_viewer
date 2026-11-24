# 코드 산책

객체지향 코드가 익숙하지 않은 사람도 작은 프로그램의 구조와 호출 흐름을 한눈에 이해할 수 있도록 만든 로컬 코드 뷰어입니다.

파일을 로컬에서만 정적으로 분석하며, 소스 코드를 실행하지 않습니다.

## 주요 기능

- **캔버스 시각화**: 파일(문서), 클래스(원), 함수·메서드(네모), 전역·클래스 변수(육각형), import(보라색 블록), 실행 시작점(파란 카드)을 작성 순서대로 펼쳐 봅니다.
- **호출·상속 점선**: 함수 본문의 호출이나 클래스의 상속 버튼을 누르면 대상까지 점선 화살표로 연결합니다. 대상을 확정할 수 없으면 회색 점선 밑줄과 함께 이유를 안내합니다.
- **단계별 학습 예제**: 상단 메뉴에서 `Python (주문)`, `Python (상속)`, `Java (주문)` 예제를 골라 시작점 → 객체 생성 → 메서드 호출 → 데이터 흐름을 코드 줄 강조와 함께 따라볼 수 있습니다.
- **폴더 탐색과 검색**: 프로젝트 폴더를 추가하면 왼쪽 트리에 계층으로 표시되며, 캔버스로 끌어놓아 배치합니다. 파일·클래스·함수 이름 검색과 호출 흐름 집중 보기를 지원합니다.
- **코드 메모와 자동 저장**: 코드 영역을 우클릭해 메모를 남기고 이동·크기 조절·검색·Markdown 내보내기를 할 수 있습니다. 작업 상태와 메모는 약 1초마다 자동 저장되며 삭제 되돌리기를 지원합니다.

## 실행 방법

### 준비 사항

- Python 3.9 이상과 최신 웹 브라우저
- **Python 분석만 사용**: 추가 패키지 설치 없이 바로 실행할 수 있습니다.
- **Java·C# 분석 포함**: 가상환경에 `requirements.txt`(`javalang`, `tree-sitter`, `tree-sitter-c-sharp`)를 설치합니다.

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python viewer.py
```

### Windows (PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe viewer.py
```

브라우저가 자동으로 열리지 않으면 터미널에 출력된 `http://127.0.0.1:...` 주소로 접속하세요. 종료는 `Ctrl+C`입니다.

## 화면 조작

- **열기·닫기**: 파일 → 클래스 → 함수 순으로 클릭해 펼칩니다. 함수 본문은 오른쪽에 선으로 이어져 표시됩니다. 상위 도형을 닫으면 하위 상태도 함께 정리됩니다.
- **이동·확대**: 빈 영역 드래그로 캔버스를 이동하고, 마우스 휠로 포인터 기준 확대·축소합니다. 도형을 드래그해 자유롭게 배치할 수 있습니다.
- **메모**: 코드 우클릭 → `메모 추가·열기`. 상단 빨간 원에 마우스를 올리면 `×`가 나타나며 클릭 시 접힙니다(📝 아이콘으로 다시 열기).
- **제거**: 파일 도형 또는 왼쪽 폴더 트리에서 우클릭해 화면에서 제거합니다(실제 디스크 파일은 삭제하지 않습니다).

## 언어별 분석 범위와 제한사항

파일당 최대 크기는 **5 MiB**이며, `.venv`, `venv`, `__pycache__`, `.git` 디렉터리는 폴더 입력에서 제외합니다. 모든 호출 연결은 정적 분석 결과이므로 실제 실행 시의 동적 대상과 다를 수 있습니다.

- **Python (`.py`)**
  - 같은 파일의 함수 호출, 클래스 생성(`Order()`), `self.메서드()`, `super().메서드()` 연결
  - 같은 파일의 단일·다중 상속(C3 MRO)과 import한 다른 파일의 부모 클래스 연결, 같은 파일 부모 메서드 재정의 표시(`재정의(부모)`)
  - 한 번만 대입한 변수(`obj = Order()`), 타입 힌트 매개변수(`item: Order`), 한 번만 대입한 인스턴스 속성(`self.attr = Engine()`)의 메서드 호출을 함수·중첩 함수·시작점에서 연결
  - 명시적인 절대·상대 import 및 별칭을 통한 파일 간 호출 연결
  - 제한: 외부 라이브러리, 동적 호출, 2단계 이상 파일 간 상속 체인은 연결하지 않고 이유를 안내합니다. 중첩 함수 자체는 별도 도형으로 표시하지 않습니다.
- **Java (`.java`)**
  - Java 8 기준 클래스·필드·생성자·메서드·`main()` 시작점·`package`·`import` 표시
  - 같은 파일의 호출, 객체 생성, 상속, 오버라이드 표시 및 기본 타입 오버로딩 해석
  - 제한: `interface`·`enum`·파일 간 호출·제네릭·가변 인자 해석은 제한됩니다.
- **C# (`.cs`)**
  - 클래스·메서드·필드·시작점·상속 표시
  - 지역 변수·매개변수·필드·`var` 타입 추적, 오버로딩 선택, 여러 파일의 네임스페이스·`using` 별칭 연결
  - 확장 메서드, 제네릭 제약, 변경되지 않은 지역 `dynamic` 변수, 정적으로 확인 가능한 `typeof → GetMethod → Invoke` 리플렉션 연결

## 예제 (`examples/`)

| 예제 | 확인할 기능 |
| --- | --- |
| `examples/example.py` | Python 클래스·함수 구조와 비동기 함수 표시 |
| `examples/call_example.py` | 같은 파일의 함수 호출 연결 |
| `examples/learning_example.py` | Python 주문 학습 예제 (5단계 가이드) |
| `examples/inheritance_example.py` | Python 상속·`super()`·재정의·함수 안 객체 호출 (5단계 가이드) |
| `examples/project_example/` | Python import 별칭과 파일 간 호출 연결 |
| `examples/OrderExample.java` | Java 클래스·필드·생성자·`main()` 구조 |
| `examples/JavaCallsExample.java` | Java 호출·상속·오버로딩 |
| `examples/LearningExample.java` | Java 주문 학습 예제 (5단계 가이드) |
| `examples/CSharpExample.cs` | C# 기본 구조와 호출 |
| `examples/csharp_project_example/` | C# 여러 파일 네임스페이스·`using` 호출 |
| `examples/csharp_advanced_example/` | C# 확장 메서드·제네릭 제약·`dynamic`·리플렉션 |

## 프로젝트 구성

```text
code-viewer/
├─ viewer.py             # 로컬 HTTP 서버 및 정적 파일/분석 API
├─ index.html            # 화면 마크업
├─ static/
│  ├─ app.css            # 스타일
│  └─ app.js             # 캔버스, 학습 가이드, 메모, 탐색 UI
├─ analyzers/
│  ├─ __init__.py        # 확장자별 분석기 라우팅
│  ├─ python.py          # Python AST 분석기
│  ├─ java.py            # Java 구조 분석기
│  ├─ java_calls.py      # Java 호출·상속·오버로딩 분석
│  ├─ csharp.py          # C# 구조 분석기
│  ├─ csharp_calls.py    # C# 여러 파일 호출 분석
│  └─ csharp_advanced.py # C# 확장 메서드·제네릭·dynamic·리플렉션
├─ examples/             # 언어별 예제 파일·폴더
├─ tests/                # Python 단위 테스트 및 JS 캔버스·브라우저 테스트
├─ requirements.txt      # Java·C# 파서 의존성
└─ usability-check.md    # 초보자 사용성 평가 과제 및 기록표
```

## 테스트

```bash
# Python 단위 테스트 (전체)
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'

# 캔버스 로직 테스트 (Node.js)
node tests/test_canvas.cjs

# 브라우저 통합 테스트 (Playwright + Chromium 필요)
node tests/test_browser.cjs
```
