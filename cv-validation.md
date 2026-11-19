# CV 프로젝트 검증 결과

가상환경·외부 라이브러리를 제외한 프로젝트 Python 소스를 읽기 전용으로 분석했습니다.

| 파일 | 표시된 호출 | 미확정 호출 |
| --- | ---: | ---: |
| tensor/check_resize.py | 10 | 10 |
| tensor/train.py | 8 | 8 |
| tensor/model/losses.py | 12 | 4 |
| tensor/model/network.py | 20 | 20 |
| tensor/model/__init__.py | 0 | 0 |
| tensor/tensor_model.py | 0 | 0 |
| tensor/detect_webcam.py | 43 | 28 |
| tensor/tensor_test2.py | 14 | 14 |
| tensor/check_labels.py | 22 | 22 |
| tensor/camera_test.py | 3 | 3 |
| tensor/tensor_test.py | 8 | 8 |
| tensor/prepare_dataset.py | 66 | 53 |
| tensor/test_model.py | 40 | 27 |
| detect_camera.py | 5 | 5 |

모든 파일의 구문 분석, 내부 연결의 함수 이름·선언 줄 일치, 호출 안내문 존재를 검사했습니다. 미확정 호출은 이유를 표시하며 연결하지 않습니다. 동적 실행 대상의 일치나 모든 외부 연결의 정확성을 보장하는 검사는 아닙니다.
