"""
KakeiBOT - 家計管理 Discord Bot

メッセージ形式: <金額> <カテゴリ> [通貨]
例: 560 家賃          → JPY (省略時デフォルト)
    10.26 食費 USD    → USD
    1200 光熱費 JPY   → JPY (明示)

コマンド一覧は !help で確認できます。
"""

import re
import subprocess
import sys
from datetime import datetime, time

import discord
from datetime import timezone, timedelta

import pytz
from discord.ext import commands, tasks

from config import Config
from setup_spreadsheet import setup as spreadsheet_setup, validate as spreadsheet_validate
from sheets_manager import SheetsManager, _get_pay_period, fmt

# 末尾の通貨コード (JPY/USD) は省略可能。省略時は DEFAULT_CURRENCY が使われる。
_CURRENCIES = "|".join(Config.SUPPORTED_CURRENCIES)
# カテゴリあり: "560 家賃" / "-10.26 食費 USD" (マイナスは取消)
EXPENSE_PATTERN = re.compile(
    rf"^(-?\d+(?:\.\d+)?)\s+(.+?)(?:\s+({_CURRENCIES}))?$", re.IGNORECASE
)
# 数字のみ (カテゴリ省略): "560" / "-560 USD" → 食費として扱う
AMOUNT_ONLY_PATTERN = re.compile(
    rf"^(-?\d+(?:\.\d+)?)(?:\s+({_CURRENCIES}))?$", re.IGNORECASE
)
INCOME_PATTERN = re.compile(
    rf"^!収入\s+(\d+(?:\.\d+)?)(?:\s+({_CURRENCIES}))?$", re.IGNORECASE
)
DEFAULT_CATEGORY = "食費"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
sheets = SheetsManager()
jst = pytz.timezone(Config.TIMEZONE)
_JST_FIXED = timezone(timedelta(hours=9))  # tasks.loop の time() 用 (pytz は LMT オフセットになるため)


# ------------------------------------------------------------------
# イベント
# ------------------------------------------------------------------


@bot.event
async def on_ready() -> None:
    print(f"[Bot] ログイン: {bot.user} (id={bot.user.id})")
    print("[Bot] スプレッドシートを検証中...")

    ok, issues = spreadsheet_validate()
    if ok:
        print("[Bot] ✅ スプレッドシートの検証OK")
    else:
        print("[Bot] ⚠️ 以下の問題が見つかりました:")
        for issue in issues:
            print(f"       - {issue}")
        print("[Bot] 🔧 自動セットアップを実行します...")
        try:
            spreadsheet_setup()
            print("[Bot] ✅ セットアップ完了")
        except Exception as exc:
            print(f"[Bot] ❌ セットアップ失敗: {exc}")
            print("[Bot] ⚠️  手動で setup_spreadsheet.py を実行してください")

    daily_report.start()
    weekly_report.start()
    monthly_report.start()


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot and not message.webhook_id:
        return
    if message.channel.id != Config.EXPENSE_CHANNEL_ID:
        await bot.process_commands(message)
        return

    content = message.content.strip()

    income_match = INCOME_PATTERN.match(content)
    if income_match:
        amount   = float(income_match.group(1))
        currency = (income_match.group(2) or Config.DEFAULT_CURRENCY).upper()
        success, error_msg = sheets.set_income(amount, currency)
        if success:
            await message.add_reaction("✅")
        else:
            await message.add_reaction("❌")
            await message.channel.send(f"⚠️ 収入の登録に失敗しました。\n```{error_msg}```")
        return

    match = EXPENSE_PATTERN.match(content)
    if match:
        amount = float(match.group(1))
        category = match.group(2).strip()
        currency = (match.group(3) or Config.DEFAULT_CURRENCY).upper()
    else:
        match = AMOUNT_ONLY_PATTERN.match(content)
        if match:
            amount = float(match.group(1))
            category = DEFAULT_CATEGORY
            currency = (match.group(2) or Config.DEFAULT_CURRENCY).upper()
        else:
            await bot.process_commands(message)
            return

    if amount < 0:
        success = sheets.delete_expense(abs(amount), category, currency)
        if success:
            await message.add_reaction("🗑️")
        else:
            await message.add_reaction("❌")
            await message.channel.send(
                f"⚠️ 該当する支出記録が見つかりませんでした。({fmt(abs(amount), currency)} / {category})",
                delete_after=10,
            )
    else:
        success = sheets.add_expense(amount, category, currency)
        if success:
            await message.add_reaction("✅")
        else:
            await message.add_reaction("❌")
            await message.channel.send("⚠️ スプレッドシートへの記録に失敗しました。")


# ------------------------------------------------------------------
# 手動コマンド
# ------------------------------------------------------------------


@bot.command(name="今日")
async def cmd_today(ctx: commands.Context) -> None:
    """本日の支出レポートを表示する。"""
    await ctx.send(sheets.get_daily_report())


@bot.command(name="今週")
async def cmd_week(ctx: commands.Context) -> None:
    """今週の支出レポートを表示する。"""
    await ctx.send(sheets.get_weekly_report())


@bot.command(name="今月")
async def cmd_month(ctx: commands.Context) -> None:
    """今月（現在の給与期間）の進行中レポートを表示する。"""
    await ctx.send(sheets.get_current_period_report())


@bot.command(name="予算")
async def cmd_budget(ctx: commands.Context, amount: str = "") -> None:
    """1日の予算を表示・設定する。引数なしで表示、金額を渡すと設定。"""
    currency = Config.DEFAULT_CURRENCY
    if not amount:
        budget = sheets.get_daily_budget(currency)
        if budget > 0:
            await ctx.send(f"💰 1日の予算: **{fmt(budget, currency)}**")
        else:
            await ctx.send(f"💰 1日の予算 ({currency}): 未設定\n`!予算 <金額>` で設定できます。")
        return

    value = float_or_none(amount)
    if value is None or value <= 0:
        await ctx.send(f"⚠️ 正しい金額を入力してください。例: `!予算 30`")
        return

    success, error_msg = sheets.set_daily_budget(value, currency)
    if success:
        await ctx.send(f"✅ 1日の予算を **{fmt(value, currency)}** に設定しました。")
    else:
        await ctx.send(f"❌ 設定に失敗しました。\n```{error_msg}```")


@bot.command(name="給料日")
async def cmd_payday(ctx: commands.Context, day: str = "") -> None:
    """給料日を表示・設定する。
    使い方: !給料日 → 現在の設定を表示
            !給料日 15 → 毎月15日に設定
    """
    if not day:
        current = sheets.get_payday()
        start, end = _get_pay_period(current, datetime.now(jst).date())
        await ctx.send(
            f"📅 給料日: 毎月 **{current}日**\n"
            f"現在の期間: {start.strftime('%m/%d')} 〜 {end.strftime('%m/%d')}"
        )
        return

    try:
        d = int(day)
    except ValueError:
        await ctx.send("⚠️ 日付は数字で入力してください。例: `!給料日 15`")
        return

    if not 1 <= d <= 31:
        await ctx.send("⚠️ 1〜31の範囲で入力してください。")
        return

    success, error_msg = sheets.set_payday(d)
    if success:
        start, end = _get_pay_period(d, datetime.now(jst).date())
        await ctx.send(
            f"✅ 給料日を **毎月{d}日** に設定しました。\n"
            f"現在の期間: {start.strftime('%m/%d')} 〜 {end.strftime('%m/%d')}"
        )
    else:
        await ctx.send(f"❌ 設定に失敗しました。\n```{error_msg}```")


@bot.command(name="通貨")
async def cmd_currency(ctx: commands.Context) -> None:
    """利用可能な通貨の一覧と使い方を表示する。"""
    currencies = ", ".join(Config.SUPPORTED_CURRENCIES)
    lines = [
        f"💱 **利用可能な通貨**: {currencies}",
        f"デフォルト: **{Config.DEFAULT_CURRENCY}**",
        "",
        "**使い方:**",
        "　`560 家賃` → JPY (省略時デフォルト)",
        "　`10.26 食費 USD` → USD",
        "　`1200 光熱費 JPY` → JPY (明示)",
    ]
    await ctx.send("\n".join(lines))


@bot.command(name="収入")
async def cmd_income(ctx: commands.Context, amount: str = "", currency: str = "") -> None:
    """今月の収入を表示・登録する。引数なしで表示、金額を渡すと登録。"""
    if not amount:
        now = datetime.now(jst)
        ym = now.strftime("%Y-%m")
        lines = [f"💴 **{now.strftime('%Y年%m月')}の収入**"]
        found = False
        for cur in Config.SUPPORTED_CURRENCIES:
            income = sheets.get_income(cur, ym)
            if income > 0:
                lines.append(f"　{cur}: {fmt(income, cur)}")
                found = True
        if not found:
            lines.append("　未登録です。`!収入 <金額>` で登録してください。")
        await ctx.send("\n".join(lines))
        return

    value = float_or_none(amount)
    if value is None or value <= 0:
        await ctx.send("⚠️ 正しい金額を入力してください。例: `!収入 1960 USD`")
        return

    cur = (currency.upper() if currency else Config.DEFAULT_CURRENCY)
    if cur not in Config.SUPPORTED_CURRENCIES:
        await ctx.send(f"⚠️ 未対応の通貨です。使用可能: {', '.join(Config.SUPPORTED_CURRENCIES)}")
        return

    success, error_msg = sheets.set_income(value, cur)
    if success:
        ym = datetime.now(jst).strftime("%Y年%m月")
        await ctx.send(f"✅ {ym}の収入を登録しました: **{fmt(value, cur)}**")
    else:
        await ctx.send(f"❌ 収入の登録に失敗しました。\n```{error_msg}```")


@bot.command(name="help", aliases=["ヘルプ"])
async def cmd_help(ctx: commands.Context) -> None:
    """コマンド一覧を表示する。"""
    cur = Config.DEFAULT_CURRENCY
    lines = [
        "📖 **コマンド一覧**",
        "",
        "**📥 支出入力** (支出チャンネルのみ)",
        "```",
        f"<金額> <カテゴリ> [通貨]   例: 10.26 食費 {cur}",
        f"<金額> [通貨]              例: 5.00 {cur}  (カテゴリ省略 → 食費)",
        "```",
        "**📊 レポート**",
        "```",
        "!今日          本日の支出",
        "!今週          今週の支出 (月〜日)",
        "!今月          今月の支出 (給与期間)",
        "```",
        "**⚙️ 設定・確認**",
        "```",
        "!予算                  1日の予算を表示",
        f"!予算 <金額>           1日の予算を設定    例: !予算 30",
        "!収入                  今月の収入を表示",
        f"!収入 <金額> [通貨]    今月の収入を登録   例: !収入 1960 {cur}",
        "!給料日                給料日を表示",
        "!給料日 <日>           給料日を設定       例: !給料日 15",
        "!通貨                  使用可能な通貨を確認",
        "```",
    ]
    await ctx.send("\n".join(lines))


@bot.command(name="update")
async def cmd_update(ctx: commands.Context) -> None:
    """GitHubから最新コードを取得してBotを再起動する。"""
    if ctx.author.id != Config.OWNER_ID:
        await ctx.send("⚠️ このコマンドは管理者のみ使用できます。")
        return

    await ctx.send("🔄 アップデートを開始します...")
    try:
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            capture_output=True,
            text=True,
            cwd="/home/s1675dis/KakeiBOT_ex",
        )
        output = result.stdout.strip() or result.stderr.strip() or "(出力なし)"
        await ctx.send(f"```{output}```")
    except Exception as e:
        await ctx.send(f"❌ git pull 失敗: {e}")
        return

    await ctx.send("♻️ 再起動します...")
    sys.exit(0)


def float_or_none(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


# ------------------------------------------------------------------
# 定期タスク
# ------------------------------------------------------------------


@tasks.loop(
    time=time(
        hour=Config.DAILY_REPORT_HOUR,
        minute=Config.DAILY_REPORT_MINUTE,
        tzinfo=_JST_FIXED,
    )
)
async def daily_report() -> None:
    """毎日設定時刻に日次レポートを送信する。"""
    channel = bot.get_channel(Config.REPORT_CHANNEL_ID)
    if channel:
        await channel.send(sheets.get_daily_report())


@tasks.loop(
    time=time(
        hour=Config.WEEKLY_REPORT_HOUR,
        minute=Config.WEEKLY_REPORT_MINUTE,
        tzinfo=_JST_FIXED,
    )
)
async def weekly_report() -> None:
    """毎週日曜日に週次レポートを送信する。"""
    if datetime.now(jst).weekday() != 6:  # 6 = Sunday
        return
    channel = bot.get_channel(Config.REPORT_CHANNEL_ID)
    if channel:
        await channel.send(sheets.get_weekly_report())


@tasks.loop(
    time=time(
        hour=Config.MONTHLY_REPORT_HOUR,
        minute=Config.MONTHLY_REPORT_MINUTE,
        tzinfo=_JST_FIXED,
    )
)
async def monthly_report() -> None:
    """給料日に前期間の月次レポートを送信する。"""
    if datetime.now(jst).day != sheets.get_payday():
        return
    channel = bot.get_channel(Config.REPORT_CHANNEL_ID)
    if channel:
        await channel.send(sheets.get_monthly_report())


if __name__ == "__main__":
    bot.run(Config.DISCORD_TOKEN)
