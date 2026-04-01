import calendar
from datetime import date as DateType
from datetime import datetime, timedelta

import gspread
import pytz
from google.oauth2.service_account import Credentials

from config import Config


# スプレッドシートのシート名
SHEET_EXPENSES = "支出記録"
SHEET_BUDGET = "予算設定"
SHEET_INCOME = "収入記録"

# 通貨ごとの表示設定
CURRENCY_SYMBOL = {"JPY": "¥", "USD": "$"}
CURRENCY_DECIMALS = {"JPY": 0, "USD": 2}


_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%Y年%m月%d日")


def _parse_date(value: str) -> DateType | None:
    """Google Sheetsから返る様々な日付形式をdateオブジェクトに変換する。"""
    for fmt_str in _DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt_str).date()
        except ValueError:
            continue
    return None


def fmt(amount: float, currency: str) -> str:
    """金額を通貨記号付きでフォーマットする。"""
    symbol = CURRENCY_SYMBOL.get(currency, currency)
    decimals = CURRENCY_DECIMALS.get(currency, 2)
    if decimals == 0:
        return f"{symbol}{amount:,.0f}"
    return f"{symbol}{amount:,.{decimals}f}"


def _now() -> datetime:
    return datetime.now(pytz.timezone(Config.TIMEZONE))


def _current_ym() -> str:
    return _now().strftime("%Y-%m")


def _make_date_clamp(year: int, month: int, day: int) -> DateType:
    """月の日数を超えないようにdateを作成する (例: 2月31日 → 2月28日)。"""
    return DateType(year, month, min(day, calendar.monthrange(year, month)[1]))


def _get_pay_period(payday: int, reference: DateType) -> tuple[DateType, DateType]:
    """paydayを起点とした、referenceが属する期間 (start, end) を返す。
    例) payday=15, reference=3/20 → (3/15, 4/14)
        payday=15, reference=3/10 → (2/15, 3/14)
    """
    if reference.day >= payday:
        start = _make_date_clamp(reference.year, reference.month, payday)
    else:
        prev_year  = reference.year if reference.month > 1 else reference.year - 1
        prev_month = reference.month - 1 or 12
        start = _make_date_clamp(prev_year, prev_month, payday)

    next_year  = start.year + (1 if start.month == 12 else 0)
    next_month = start.month % 12 + 1
    end = _make_date_clamp(next_year, next_month, payday) - timedelta(days=1)
    return start, end


def _income_from_records(records: list[dict], currency: str, year_month: str) -> float:
    for row in records:
        if (str(row.get("年月", "")).strip() == year_month
                and str(row.get("通貨", "")).strip().upper() == currency):
            return float(row.get("金額", 0))
    return 0.0


class SheetsManager:
    def __init__(self) -> None:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(
            Config.GOOGLE_CREDENTIALS_FILE, scopes=scopes
        )
        self._client = gspread.authorize(creds)
        self._spreadsheet = self._client.open_by_key(Config.SPREADSHEET_ID)

    def _expenses_sheet(self) -> gspread.Worksheet:
        return self._spreadsheet.worksheet(SHEET_EXPENSES)

    def _budget_sheet(self) -> gspread.Worksheet:
        return self._spreadsheet.worksheet(SHEET_BUDGET)

    def _income_sheet(self) -> gspread.Worksheet:
        return self._spreadsheet.worksheet(SHEET_INCOME)

    # ------------------------------------------------------------------
    # 書き込み
    # ------------------------------------------------------------------

    def add_expense(self, amount: float, category: str, currency: str = "JPY") -> bool:
        """支出を記録する。成功したら True を返す。"""
        currency = currency.upper()
        if currency not in Config.SUPPORTED_CURRENCIES:
            currency = Config.DEFAULT_CURRENCY
        try:
            now = _now()
            self._expenses_sheet().append_row(
                [now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), category, amount, currency],
                value_input_option="USER_ENTERED",
            )
            return True
        except Exception as exc:
            print(f"[SheetsManager] add_expense error: {exc}")
            return False

    def set_income(self, amount: float, currency: str, year_month: str | None = None) -> tuple[bool, str]:
        """指定年月の収入を記録する（既存行があれば上書き）。
        year_month は "YYYY-MM" 形式。省略時は今月。
        戻り値: (成功フラグ, エラーメッセージ)
        """
        currency = currency.upper()
        if year_month is None:
            year_month = _current_ym()
        try:
            sheet = self._income_sheet()
            records = sheet.get_all_records()
            for i, row in enumerate(records, start=2):  # ヘッダー行を除くため2始まり
                if str(row.get("年月", "")).strip() == year_month and \
                        str(row.get("通貨", "")).strip().upper() == currency:
                    sheet.update(f"B{i}", [[amount]])
                    return True, ""
            sheet.append_row([year_month, amount, currency], value_input_option="USER_ENTERED")
            return True, ""
        except Exception as exc:
            print(f"[SheetsManager] set_income error: {exc}")
            return False, str(exc)

    def get_income(self, currency: str, year_month: str | None = None) -> float:
        """指定年月・通貨の収入を返す。記録がなければ 0.0。"""
        currency = currency.upper()
        if year_month is None:
            year_month = _current_ym()
        try:
            records = self._income_sheet().get_all_records()
            for row in records:
                if str(row.get("年月", "")).strip() == year_month and \
                        str(row.get("通貨", "")).strip().upper() == currency:
                    return float(row.get("金額", 0))
        except Exception as exc:
            print(f"[SheetsManager] get_income error: {exc}")
        return 0.0

    # ------------------------------------------------------------------
    # 読み取り
    # ------------------------------------------------------------------

    def get_food_budget(self) -> float:
        """予算設定シートから「食費予算」（1日あたり）を取得する。"""
        try:
            records = self._budget_sheet().get_all_records()
            for row in records:
                if str(row.get("項目", "")).strip() == "食費予算":
                    return float(row.get("金額", 0))
        except Exception as exc:
            print(f"[SheetsManager] get_food_budget error: {exc}")
        return 0.0

    def set_food_budget(self, amount: float) -> tuple[bool, str]:
        """食費予算（1日あたり）を設定する（既存行があれば上書き）。"""
        try:
            sheet = self._budget_sheet()
            records = sheet.get_all_records()
            for i, row in enumerate(records, start=2):
                if str(row.get("項目", "")).strip() == "食費予算":
                    sheet.update(f"B{i}", [[amount]])
                    return True, ""
            sheet.append_row(["食費予算", amount], value_input_option="USER_ENTERED")
            return True, ""
        except Exception as exc:
            print(f"[SheetsManager] set_food_budget error: {exc}")
            return False, str(exc)

    def get_payday(self) -> int:
        """給料日 (1〜31) を返す。未設定の場合は 1。"""
        try:
            records = self._budget_sheet().get_all_records()
            for row in records:
                if str(row.get("項目", "")).strip() == "給料日":
                    return max(1, min(31, int(row.get("金額", 1))))
        except Exception as exc:
            print(f"[SheetsManager] get_payday error: {exc}")
        return 1

    def set_payday(self, day: int) -> tuple[bool, str]:
        """給料日を設定する。"""
        day = max(1, min(31, day))
        try:
            sheet = self._budget_sheet()
            records = sheet.get_all_records()
            for i, row in enumerate(records, start=2):
                if str(row.get("項目", "")).strip() == "給料日":
                    sheet.update(f"B{i}", [[day]])
                    return True, ""
            sheet.append_row(["給料日", day], value_input_option="USER_ENTERED")
            return True, ""
        except Exception as exc:
            print(f"[SheetsManager] set_payday error: {exc}")
            return False, str(exc)

    def get_default_currency(self) -> str:
        """スプレッドシートに保存されたデフォルト通貨を返す。未設定の場合は Config の値。"""
        try:
            records = self._budget_sheet().get_all_records()
            for row in records:
                if str(row.get("項目", "")).strip() == "デフォルト通貨":
                    val = str(row.get("金額", "")).strip().upper()
                    if val in Config.SUPPORTED_CURRENCIES:
                        return val
        except Exception as exc:
            print(f"[SheetsManager] get_default_currency error: {exc}")
        return Config.DEFAULT_CURRENCY

    def set_default_currency(self, currency: str) -> tuple[bool, str]:
        """デフォルト通貨をスプレッドシートに保存する。"""
        currency = currency.upper()
        try:
            sheet = self._budget_sheet()
            records = sheet.get_all_records()
            for i, row in enumerate(records, start=2):
                if str(row.get("項目", "")).strip() == "デフォルト通貨":
                    sheet.update(f"B{i}", [[currency]])
                    return True, ""
            sheet.append_row(["デフォルト通貨", currency], value_input_option="USER_ENTERED")
            return True, ""
        except Exception as exc:
            print(f"[SheetsManager] set_default_currency error: {exc}")
            return False, str(exc)

    def delete_expense(self, amount: float, category: str, currency: str) -> bool:
        """条件に一致する最新の支出行を削除する。見つからなければ False を返す。"""
        try:
            sheet = self._expenses_sheet()
            records = sheet.get_all_records()
            match_row = None
            for i, row in enumerate(records, start=2):
                if (float(row.get("金額", 0)) == amount
                        and str(row.get("カテゴリ", "")).strip() == category
                        and str(row.get("通貨", "")).strip().upper() == currency):
                    match_row = i  # 最後にマッチした行（最新入力）を対象にする
            if match_row is not None:
                sheet.delete_rows(match_row)
                return True
            return False
        except Exception as exc:
            print(f"[SheetsManager] delete_expense error: {exc}")
            return False

    def _get_budget_records(self) -> list[dict]:
        """予算設定シートのレコードを1回だけ取得する（内部用）。"""
        try:
            return self._budget_sheet().get_all_records()
        except Exception as exc:
            print(f"[SheetsManager] _get_budget_records error: {exc}")
            return []

    def _food_budget_from_records(self, records: list[dict]) -> float:
        """レコードから食費予算を返す（API呼び出し節約用）。"""
        for row in records:
            if str(row.get("項目", "")).strip() == "食費予算":
                return float(row.get("金額", 0))
        return 0.0

    def _get_expenses_for_dates(self, start_date: str, end_date: str) -> list[dict]:
        """start_date〜end_date (YYYY-MM-DD) の支出レコードを返す。
        日付はdateオブジェクトで比較するため、Sheetsのロケール形式に依存しない。
        """
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
            records = self._expenses_sheet().get_all_records()
            result = []
            for r in records:
                d = _parse_date(str(r.get("日付", "")))
                if d is not None and start <= d <= end:
                    result.append(r)
            return result
        except Exception as exc:
            print(f"[SheetsManager] _get_expenses_for_dates error: {exc}")
            return []

    # ------------------------------------------------------------------
    # 集計ヘルパー
    # ------------------------------------------------------------------

    def _aggregate(
        self, records: list[dict]
    ) -> dict[str, tuple[float, dict[str, float]]]:
        """レコードを通貨ごとに集計する。
        戻り値: {currency: (total, {category: amount})}
        """
        result: dict[str, tuple[float, dict[str, float]]] = {}
        for r in records:
            currency = str(r.get("通貨", Config.DEFAULT_CURRENCY)).upper()
            if currency not in Config.SUPPORTED_CURRENCIES:
                currency = Config.DEFAULT_CURRENCY
            amt = float(r.get("金額", 0))
            cat = str(r.get("カテゴリ", "その他"))

            total, by_cat = result.get(currency, (0.0, {}))
            total += amt
            by_cat[cat] = by_cat.get(cat, 0.0) + amt
            result[currency] = (total, by_cat)
        return result

    def _build_currency_section(
        self,
        currency: str,
        total: float,
        by_category: dict[str, float],
        food_budget: float,
        days: int = 1,
    ) -> list[str]:
        """通貨1つ分のレポートブロックを生成する。食費予算は食費カテゴリにのみ適用。"""
        lines: list[str] = []
        food_total = by_category.get("食費", 0.0)
        budget_total = food_budget * days

        lines.append(f"**[{currency}]**")
        lines.append(f"支出合計: {fmt(total, currency)}")

        if by_category:
            for cat, amt in sorted(by_category.items(), key=lambda x: -x[1]):
                lines.append(f"　{cat}: {fmt(amt, currency)}")

        if budget_total > 0:
            lines.append(f"食費予算: {fmt(budget_total, currency)}")
            diff = budget_total - food_total
            if diff >= 0:
                lines.append(f"✅ 食費 {fmt(diff, currency)} 節約")
            else:
                lines.append(f"⚠️ 食費 {fmt(abs(diff), currency)} オーバー")

        return lines

    # ------------------------------------------------------------------
    # レポート
    # ------------------------------------------------------------------

    def get_daily_report(self) -> str:
        today = _now()
        today_str = today.strftime("%Y-%m-%d")

        records = self._get_expenses_for_dates(today_str, today_str)
        aggregated = self._aggregate(records)
        budget_records = self._get_budget_records()
        food_budget = self._food_budget_from_records(budget_records)

        lines = [f"📊 **{today.strftime('%Y年%m月%d日')}の支出レポート**"]

        for currency in Config.SUPPORTED_CURRENCIES:
            if currency not in aggregated:
                continue
            total, by_cat = aggregated[currency]
            lines.append("")
            lines.extend(self._build_currency_section(currency, total, by_cat, food_budget, days=1))

        if not aggregated:
            lines.append("本日の支出はありません。")

        return "\n".join(lines)

    def get_weekly_report(self) -> str:
        now = _now()
        week_start = now - timedelta(days=now.weekday())
        week_end = week_start + timedelta(days=6)

        records = self._get_expenses_for_dates(
            week_start.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")
        )
        aggregated = self._aggregate(records)
        food_budget = self.get_food_budget()

        lines = [f"📅 **今週の支出レポート**"]
        lines.append(
            f"期間: {week_start.strftime('%m/%d')} 〜 {week_end.strftime('%m/%d')}"
        )

        for currency in Config.SUPPORTED_CURRENCIES:
            if currency not in aggregated:
                continue
            total, by_cat = aggregated[currency]
            lines.append("")
            lines.extend(
                self._build_currency_section(currency, total, by_cat, food_budget, days=7)
            )

        if not aggregated:
            lines.append("今週の支出はありません。")

        return "\n".join(lines)

    def get_current_period_report(self) -> str:
        """現在の給与期間（今月）の進行中レポートを返す。"""
        today = _now().date()
        payday = self.get_payday()
        start, end = _get_pay_period(payday, today)
        days_total = (end - start).days + 1
        days_elapsed = (today - start).days + 1

        records = self._get_expenses_for_dates(
            start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
        )
        aggregated = self._aggregate(records)
        budget_records = self._get_budget_records()
        food_budget = self._food_budget_from_records(budget_records)
        try:
            income_records = self._income_sheet().get_all_records()
        except Exception as exc:
            print(f"[SheetsManager] get_current_period_report income fetch error: {exc}")
            income_records = []

        period_ym = start.strftime("%Y-%m")
        lines = [f"📊 **今月の支出レポート**"]
        lines.append(
            f"期間: {start.strftime('%m/%d')} 〜 {end.strftime('%m/%d')}"
            f"　({days_elapsed}/{days_total}日経過)"
        )

        for currency in Config.SUPPORTED_CURRENCIES:
            expense_total, by_cat = aggregated.get(currency, (0.0, {}))
            income = _income_from_records(income_records, currency, period_ym)

            if expense_total == 0.0 and income == 0.0:
                continue

            lines.append("")
            lines.append(f"**[{currency}]**")
            if income > 0:
                lines.append(f"収入: {fmt(income, currency)}")
            lines.append(f"支出合計: {fmt(expense_total, currency)}")
            if by_cat:
                for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
                    lines.append(f"　{cat}: {fmt(amt, currency)}")

            food_total = by_cat.get("食費", 0.0)
            food_budget_elapsed = food_budget * days_elapsed
            if food_budget_elapsed > 0:
                lines.append(f"食費予算: {fmt(food_budget_elapsed, currency)}  (累計{days_elapsed}日)")
                diff = food_budget_elapsed - food_total
                if diff >= 0:
                    lines.append(f"✅ 食費 {fmt(diff, currency)} 節約中")
                else:
                    lines.append(f"⚠️ 食費 {fmt(abs(diff), currency)} オーバー")

            lines.append("")
            if income > 0:
                remaining = income - expense_total
                if remaining >= 0:
                    lines.append(f"💰 残り使える額: **{fmt(remaining, currency)}**")
                else:
                    lines.append(f"⚠️ 収入オーバー: **{fmt(abs(remaining), currency)}**")

        if len(lines) == 2:
            lines.append("支出はありません。")

        return "\n".join(lines)

    def get_monthly_report(self) -> str:
        """直前の給与期間の確定レポートを返す（給料日の定期配信用）。"""
        today = _now().date()
        payday = self.get_payday()
        # 昨日が属する期間 = 給料日当日に実行すると直前の完了期間になる
        start, end = _get_pay_period(payday, today - timedelta(days=1))
        days_total = (end - start).days + 1
        target_ym = start.strftime("%Y-%m")

        records = self._get_expenses_for_dates(
            start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        )
        aggregated = self._aggregate(records)
        food_budget = self.get_food_budget()
        try:
            income_records = self._income_sheet().get_all_records()
        except Exception as exc:
            print(f"[SheetsManager] get_monthly_report income fetch error: {exc}")
            income_records = []

        lines = [f"📆 **月次レポート ({start.strftime('%m/%d')} 〜 {end.strftime('%m/%d')})**"]

        for currency in Config.SUPPORTED_CURRENCIES:
            expense_total, by_cat = aggregated.get(currency, (0.0, {}))
            income = _income_from_records(income_records, currency, target_ym)

            if expense_total == 0.0 and income == 0.0:
                continue

            lines.append("")
            lines.append(f"**[{currency}]**")
            if income > 0:
                lines.append(f"収入: {fmt(income, currency)}")
            lines.append(f"支出合計: {fmt(expense_total, currency)}")
            if by_cat:
                for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
                    lines.append(f"　{cat}: {fmt(amt, currency)}")

            food_total = by_cat.get("食費", 0.0)
            food_budget_total = food_budget * days_total
            if food_budget_total > 0:
                lines.append(f"食費予算: {fmt(food_budget_total, currency)}")
                diff = food_budget_total - food_total
                if diff >= 0:
                    lines.append(f"✅ 食費 {fmt(diff, currency)} 節約")
                else:
                    lines.append(f"⚠️ 食費 {fmt(abs(diff), currency)} オーバー")

            lines.append("")
            if income > 0:
                savings = income - expense_total
                if savings >= 0:
                    lines.append(f"💰 今月の貯金: **{fmt(savings, currency)}**")
                else:
                    lines.append(f"⚠️ 収入オーバー: **{fmt(abs(savings), currency)}**")

        if len(lines) == 1:
            lines.append("先月の支出・収入はありません。")

        return "\n".join(lines)
