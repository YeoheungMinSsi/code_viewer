"""Read-only validation of the sibling CV project's tracked/unignored Python sources."""
import ast
import subprocess
from pathlib import Path
from xml.etree.ElementTree import fromstring
from viewer import outline

rows = []
for name in subprocess.check_output(['rg', '--files', '../cv', '-g', '*.py'], text=True).splitlines():
    path = Path(name)
    source = path.read_bytes()
    root = fromstring('<root>' + outline(source) + '</root>')
    definitions = {str(n.lineno): n.name for n in ast.walk(ast.parse(source))
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    links = root.findall('.//button')
    for link in links:
        target = link.attrib['data-target']
        if target.isdigit():
            assert target in definitions, (path, target)
            assert (link.text or '').split('.')[-1] == definitions[target], (path, link.text, target)
        assert link.attrib.get('title'), (path, link.text)
    unknown = sum(n.attrib['data-target'].startswith('?') for n in links)
    rows.append(f'| {path.relative_to("../cv")} | {len(links)} | {unknown} |')
Path('cv-validation.md').write_text(
    '# CV 프로젝트 검증 결과\n\n'
    '가상환경·외부 라이브러리를 제외한 프로젝트 Python 소스를 읽기 전용으로 분석했습니다.\n\n'
    '| 파일 | 표시된 호출 | 미확정 호출 |\n| --- | ---: | ---: |\n' +
    '\n'.join(rows) +
    '\n\n모든 파일의 구문 분석, 내부 연결의 함수 이름·선언 줄 일치, 호출 안내문 존재를 검사했습니다. '
    '미확정 호출은 이유를 표시하며 연결하지 않습니다. 동적 실행 대상의 일치나 모든 외부 연결의 정확성을 보장하는 검사는 아닙니다.\n')
print(f'PASS: {len(rows)} CV source files')
