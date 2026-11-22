"""Падение UI-шага: путь шагов в тексте ошибки, короткий traceback, неоднозначный локатор, trace."""

import json

MISSING_BUTTON = '''
@step("Открыть окно «Тест»")
def open_window(page):
    BasePage(page).element("Кнопка «Нет»", "#missing", timeout=1).click()


def test_case(page):
    page.set_content("<button>A</button>")
    open_window(page)
'''

NO_STEP = '''
def test_case(page):
    page.set_content("<button>A</button>")
    BasePage(page).element("Кнопка «Нет»", "#missing", timeout=1).click()
'''

CAUGHT_THEN_FAIL = '''
@step("Первый")
def first(page):
    BasePage(page).element("Кнопка «Нет»", "#missing", timeout=1).click()


@step("Второй")
def second(page):
    BasePage(page).element("Кнопка «Нет»", "#missing", timeout=1).click()


def test_case(page):
    page.set_content("<button>A</button>")
    try:
        first(page)
    except AssertionError:
        pass
    second(page)
'''


class TestStepPath:
    def test_failure_message_has_step_path(self, run_ui):
        result = run_ui(MISSING_BUTTON)
        result.assert_outcomes(failed=1)
        result.stdout.fnmatch_lines(["*Открыть окно «Тест» → Клик → Кнопка «Нет»: не дождались за 1 с.*"])

    def test_failure_outside_step_has_no_path(self, run_ui):
        result = run_ui(NO_STEP)
        result.assert_outcomes(failed=1)
        result.stdout.fnmatch_lines(["*AssertionError: Клик → Кнопка «Нет»: не дождались за 1 с.*"])

    def test_caught_step_does_not_leak_into_next_failure(self, run_ui):
        result = run_ui(CAUGHT_THEN_FAIL)
        result.assert_outcomes(failed=1)
        result.stdout.fnmatch_lines(["*AssertionError: Второй → Клик → Кнопка «Нет»*"])
        result.stdout.no_fnmatch_line("*Первый → Второй*")


TWO_BUTTONS_CLICK = '''
def test_case(page):
    page.set_content("<button>A</button><button>A</button>")
    BasePage(page).element("Кнопка «A»", "button", timeout=1).click()
'''

TWO_BUTTONS_CHECK = '''
def test_case(page):
    page.set_content("<button>A</button><button>A</button>")
    BasePage(page).element("Кнопка «A»", "button", timeout=1).check_visible()
'''

SECRET_FILL = '''
import os


def test_case(page):
    page.set_content("<button>A</button>")
    BasePage(page).element("Пароль", "#missing", timeout=1).fill(os.environ["QA_TEST_SECRET"], secret=True)
'''


class TestShortFailure:
    def test_ambiguous_locator_reports_count(self, run_ui):
        result = run_ui(TWO_BUTTONS_CLICK)
        result.assert_outcomes(failed=1)
        result.stdout.fnmatch_lines(["*Клик → Кнопка «A»: найдено 2 элементов, ожидался 1.*"])

    def test_ambiguous_locator_in_check(self, run_ui):
        result = run_ui(TWO_BUTTONS_CHECK)
        result.assert_outcomes(failed=1)
        result.stdout.fnmatch_lines(["*Проверка: виден → Кнопка «A»: найдено 2 элементов, ожидался 1.*"])

    def test_traceback_hides_harness_frames(self, run_ui):
        result = run_ui(MISSING_BUTTON, "--tb=short")
        result.assert_outcomes(failed=1)
        result.stdout.no_fnmatch_line("*qa/layers/ui.py*")
        result.stdout.no_fnmatch_line("*The above exception was the direct cause*")
        result.stdout.fnmatch_lines(["*test_case.py:*"])  # последний видимый кадр — строка вложенного теста

    def test_secret_fill_value_not_shown(self, run_ui, monkeypatch):
        # пароль приходит не из исходника теста: строку теста traceback показывает всегда
        monkeypatch.setenv("QA_TEST_SECRET", "S3cr3t-value")
        result = run_ui(SECRET_FILL, "--tb=long")
        result.assert_outcomes(failed=1)
        assert "S3cr3t-value" not in result.stdout.str()


PASSING = '''
def test_case(page):
    page.set_content("<button>A</button>")
    BasePage(page).element("Кнопка «A»", "button", timeout=1).click()
'''


def has_trace(attachments: list[dict]) -> bool:
    return any(attachment["name"] == "trace" for attachment in attachments)


class TestTraceInAllure:
    def test_failed_test_has_trace_attachment(self, run_ui, pytester, allure_attachments):
        results = pytester.path / "ar"
        result = run_ui(MISSING_BUTTON, f"--alluredir={results}")
        result.assert_outcomes(failed=1)
        assert has_trace(allure_attachments(results))

    def test_passed_test_has_no_trace(self, run_ui, pytester, allure_attachments):
        results = pytester.path / "ar"
        result = run_ui(PASSING, f"--alluredir={results}")
        result.assert_outcomes(passed=1)
        assert not has_trace(allure_attachments(results))

    def test_explicit_tracing_off_respected(self, run_ui, pytester, allure_attachments):
        results = pytester.path / "ar"
        result = run_ui(MISSING_BUTTON, "--tracing", "off", f"--alluredir={results}")
        result.assert_outcomes(failed=1)
        assert not has_trace(allure_attachments(results))

    def test_tracing_off_in_ini_addopts_respected(self, run_ui, pytester, allure_attachments):
        pytester.makeini("[pytest]\naddopts = -p no:cacheprovider --tracing off\n")  # проект задал в pytest.ini
        results = pytester.path / "ar"
        result = run_ui(MISSING_BUTTON, f"--alluredir={results}")
        result.assert_outcomes(failed=1)
        assert not has_trace(allure_attachments(results))


def find_step(node: dict, title: str) -> dict | None:
    for step in node.get("steps", []):
        if step["name"] == title:
            return step
        found = find_step(step, title)
        if found:
            return found
    return None


class TestAllureStepStatus:
    def test_failed_action_step_is_failed_with_readable_message(self, run_ui, pytester):
        results = pytester.path / "ar"
        result = run_ui(MISSING_BUTTON, f"--alluredir={results}")
        result.assert_outcomes(failed=1)
        test_result = json.loads(next(results.glob("*-result.json")).read_text(encoding="utf-8"))
        step = find_step(test_result, "Клик → Кнопка «Нет»")
        assert step["status"] == "failed"  # красный, а не broken: это упавшая проверка, не сбой окружения
        assert "не дождались за 1 с." in step["statusDetails"]["message"]
