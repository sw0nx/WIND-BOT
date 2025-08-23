# bot_vending_full.py
import os
import asyncio
import aiosqlite
import datetime as dt
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

# ============ 환경설정 ============
TOKEN = os.getenv("BOT_TOKEN")  # 환경변수에 토큰 넣기
GUILD_ID = int(os.getenv("GUILD_ID", "0"))      # 슬래시 동기화용(옵션)
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))  # 결제/구매 로그 채널
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0"))    # 관리자 롤(없으면 모든 유저 제한)
DB_PATH = os.getenv("DB_PATH", "vending.db")

INTENTS = discord.Intents.default()
INTENTS.message_content = False
INTENTS.members = True
bot = commands.Bot(command_prefix="!", intents=INTENTS)

# ============ DB ============

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
  user_id INTEGER PRIMARY KEY,
  balance INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  price INTEGER NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

-- 코드 재고 풀 (각 행이 1개의 판매코드)
CREATE TABLE IF NOT EXISTS stock_codes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL,
  code TEXT NOT NULL,
  used INTEGER NOT NULL DEFAULT 0,
  used_by INTEGER,
  used_at TEXT,
  FOREIGN KEY(product_id) REFERENCES products(id)
);

-- 충전핀
CREATE TABLE IF NOT EXISTS topup_pins (
  pin TEXT PRIMARY KEY,
  amount INTEGER NOT NULL,
  used INTEGER NOT NULL DEFAULT 0,
  used_by INTEGER,
  used_at TEXT
);

-- 구매/충전/환불 등 원장
CREATE TABLE IF NOT EXISTS ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  type TEXT NOT NULL, -- 'BUY','TOPUP','REFUND'
  amount INTEGER NOT NULL,
  meta TEXT,
  created_at TEXT NOT NULL
);

-- 주문(구매 결과)
CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  product_id INTEGER NOT NULL,
  price INTEGER NOT NULL,
  code_id INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(product_id) REFERENCES products(id),
  FOREIGN KEY(code_id) REFERENCES stock_codes(id)
);
"""

async def db():
    return await aiosqlite.connect(DB_PATH)

async def db_init():
    async with await db() as con:
        await con.executescript(SCHEMA_SQL)
        await con.commit()

async def get_or_create_user(uid: int):
    async with await db() as con:
        cur = await con.execute("SELECT user_id,balance FROM users WHERE user_id=?", (uid,))
        row = await cur.fetchone()
        if row:
            return row[0], row[1]
        now = dt.datetime.utcnow().isoformat()
        await con.execute("INSERT INTO users(user_id,balance,created_at) VALUES(?,?,?)", (uid, 0, now))
        await con.commit()
        return uid, 0

async def user_balance(uid: int) -> int:
    await get_or_create_user(uid)
    async with await db() as con:
        cur = await con.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        (bal,) = await cur.fetchone()
        return bal

async def change_balance(uid: int, delta: int, typ: str, meta: str = ""):
    async with await db() as con:
        await con.execute("BEGIN IMMEDIATE")
        # 보장: 행 잠금으로 경합 방지
        cur = await con.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        row = await cur.fetchone()
        if not row:
            now = dt.datetime.utcnow().isoformat()
            await con.execute("INSERT INTO users(user_id,balance,created_at) VALUES(?,?,?)", (uid, 0, now))
            bal = 0
        else:
            bal = row[0]
        new_bal = bal + delta
        if new_bal < 0:
            await con.execute("ROLLBACK")
            raise ValueError("INSUFFICIENT")
        await con.execute("UPDATE users SET balance=? WHERE user_id=?", (new_bal, uid))
        now = dt.datetime.utcnow().isoformat()
        await con.execute(
            "INSERT INTO ledger(user_id,type,amount,meta,created_at) VALUES(?,?,?,?,?)",
            (uid, typ, delta, meta, now)
        )
        await con.commit()
        return new_bal

# ============ UI 컴포넌트 ============

class VendingView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.button(label="정보", emoji="ℹ️", style=discord.ButtonStyle.secondary, custom_id="info")
    async def info(self, interaction: discord.Interaction, button: discord.ui.Button):
        bal = await user_balance(interaction.user.id)
        await interaction.response.send_message(
            f"**자판기 안내**\n- 현재 잔액: **{bal}원**\n- 💳 충전: 충전핀 입력으로 잔액이 올라갑니다.\n- 🛒 구매: 상품을 선택하면 재고 코드가 DM으로 지급됩니다.",
            ephemeral=True
        )

    @discord.ui.button(label="충전", emoji="💳", style=discord.ButtonStyle.primary, custom_id="topup")
    async def topup(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TopupModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="구매", emoji="🛒", style=discord.ButtonStyle.success, custom_id="buy")
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 상품 불러와서 드롭다운
        async with await db() as con:
            cur = await con.execute("SELECT id,name,price,(SELECT COUNT(1) FROM stock_codes s WHERE s.product_id=p.id AND s.used=0) AS left FROM products p WHERE enabled=1 ORDER BY id")
            rows = await cur.fetchall()
        if not rows:
            return await interaction.response.send_message("판매 중인 상품이 없습니다.", ephemeral=True)
        options = []
        for pid, name, price, left in rows:
            label = f"{name} - {price}원"
            desc = f"남은수량 {left}개"
            options.append(discord.SelectOption(label=label, description=desc, value=str(pid), emoji="🧾" if left>0 else "⛔"))
        view = discord.ui.View(timeout=60)
        select = ProductSelect(options)
        view.add_item(select)
        await interaction.response.send_message("구매할 상품을 선택하세요.", view=view, ephemeral=True)

class ProductSelect(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption]):
        super().__init__(placeholder="상품 선택", min_values=1, max_values=1, options=options, custom_id="product_select")

    async def callback(self, interaction: discord.Interaction):
        pid = int(self.values[0])
        # 실제 구매 처리
        try:
            order_id, code_text, new_bal = await process_purchase(interaction.user.id, pid)
        except ValueError as e:
            msg = "알 수 없는 오류"
            if str(e) == "NO_STOCK": msg = "해당 상품 재고가 없습니다."
            if str(e) == "INSUFFICIENT": msg = "잔액이 부족합니다."
            return await interaction.response.edit_message(content=msg, view=None)
        # DM 발송
        try:
            await interaction.user.send(f"구매 완료! 주문번호 #{order_id}\n코드: `{code_text}`")
        except:
            pass
        await interaction.response.edit_message(content=f"구매 완료! DM을 확인하세요. (잔액: {new_bal}원)", view=None)
        await log_purchase(interaction.guild, interaction.user, order_id)

async def process_purchase(uid: int, product_id: int):
    # 트랜잭션: 재고 하나 픽, 잔액 차감, 주문 기록
    async with await db() as con:
        await con.execute("BEGIN IMMEDIATE")
        # 상품/가격
        cur = await con.execute("SELECT price FROM products WHERE id=? AND enabled=1", (product_id,))
        row = await cur.fetchone()
        if not row:
            await con.execute("ROLLBACK")
            raise ValueError("NO_STOCK")
        price = row[0]
        # 유저/잔액
        cur = await con.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        row = await cur.fetchone()
        bal = row[0] if row else 0
        if bal < price:
            await con.execute("ROLLBACK")
            raise ValueError("INSUFFICIENT")
        # 재고 하나 집기
        cur = await con.execute("SELECT id,code FROM stock_codes WHERE product_id=? AND used=0 LIMIT 1", (product_id,))
        code_row = await cur.fetchone()
        if not code_row:
            await con.execute("ROLLBACK")
            raise ValueError("NO_STOCK")
        code_id, code_text = code_row
        # 잔액 차감
        new_bal = bal - price
        if row is None:
            now = dt.datetime.utcnow().isoformat()
            await con.execute("INSERT INTO users(user_id,balance,created_at) VALUES(?,?,?)", (uid, new_bal, now))
        else:
            await con.execute("UPDATE users SET balance=? WHERE user_id=?", (new_bal, uid))
        # 재고 사용 처리
        now = dt.datetime.utcnow().isoformat()
        await con.execute("UPDATE stock_codes SET used=1, used_by=?, used_at=? WHERE id=?", (uid, now, code_id))
        # 주문/원장
        await con.execute("INSERT INTO orders(user_id,product_id,price,code_id,created_at) VALUES(?,?,?,?,?)",
                          (uid, product_id, price, code_id, now))
        order_id = (await con.execute("SELECT last_insert_rowid()")).fetchone()
        order_id = (await order_id).__anext__()  # trick to get single value in aiosqlite
        await con.execute("INSERT INTO ledger(user_id,type,amount,meta,created_at) VALUES(?,?,?,?,?)",
                          (uid, "BUY", -price, f"product_id={product_id},code_id={code_id}", now))
        await con.commit()
    return order_id[0], code_text, new_bal

async def log_purchase(guild: Optional[discord.Guild], user: discord.User, order_id: int):
    if not guild or not LOG_CHANNEL_ID:
        return
    ch = guild.get_channel(LOG_CHANNEL_ID)
    if ch:
        await ch.send(f"🧾 **구매 로그** | 주문 #{order_id} | {user.mention}")

# ============ 모달: 충전 ============

class TopupModal(discord.ui.Modal, title="충전핀 입력"):
    pin = discord.ui.TextInput(label="충전핀", placeholder="예) ABCD-1234-XY", required=True, min_length=4, max_length=64)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount, new_bal = await redeem_pin(interaction.user.id, str(self.pin))
        except ValueError as e:
            msg = "유효하지 않은 핀입니다."
            if str(e) == "PIN_USED": msg = "이미 사용된 핀입니다."
            return await interaction.response.send_message(msg, ephemeral=True)
        await interaction.response.send_message(f"충전 완료! +{amount}원 (잔액: {new_bal}원)", ephemeral=True)
        # 로그
        if LOG_CHANNEL_ID and interaction.guild:
            ch = interaction.guild.get_channel(LOG_CHANNEL_ID)
            if ch: await ch.send(f"💳 **충전 로그** | {interaction.user.mention} +{amount}원")

async def redeem_pin(uid: int, pin: str):
    async with await db() as con:
        await con.execute("BEGIN IMMEDIATE")
        cur = await con.execute("SELECT amount,used FROM topup_pins WHERE pin=?", (pin,))
        row = await cur.fetchone()
        if not row:
            await con.execute("ROLLBACK"); raise ValueError("PIN_INVALID")
        amount, used = row
        if used: 
            await con.execute("ROLLBACK"); raise ValueError("PIN_USED")
        # 잔액 증가
        cur = await con.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        r = await cur.fetchone()
        bal = r[0] if r else 0
        new_bal = bal + amount
        now = dt.datetime.utcnow().isoformat()
        if r is None:
            await con.execute("INSERT INTO users(user_id,balance,created_at) VALUES(?,?,?)", (uid, new_bal, now))
        else:
            await con.execute("UPDATE users SET balance=? WHERE user_id=?", (new_bal, uid))
        await con.execute("UPDATE topup_pins SET used=1, used_by=?, used_at=? WHERE pin=?", (uid, now, pin))
        await con.execute("INSERT INTO ledger(user_id,type,amount,meta,created_at) VALUES(?,?,?,?,?)",
                          (uid, "TOPUP", amount, f"pin={pin}", now))
        await con.commit()
    return amount, new_bal

# ============ 슬래시 커맨드 ============

@app_commands.guilds(discord.Object(id=GUILD_ID)) if GUILD_ID else (lambda x: x)
@bot.tree.command(name="자판기", description="버튼 메뉴를 엽니다.")
async def vending_cmd(interaction: discord.Interaction):
    view = VendingView()
    await interaction.response.send_message("원하는 메뉴를 선택하세요.", view=view, ephemeral=True)

# --- 유틸/조회
@app_commands.guilds(discord.Object(id=GUILD_ID)) if GUILD_ID else (lambda x: x)
@bot.tree.command(name="잔액", description="내 잔액을 확인합니다.")
async def balance_cmd(interaction: discord.Interaction):
    bal = await user_balance(interaction.user.id)
    await interaction.response.send_message(f"현재 잔액: **{bal}원**", ephemeral=True)

# ============ 관리자 전용 ============

def admin_only():
    async def predicate(interaction: discord.Interaction):
        if ADMIN_ROLE_ID == 0:
            return interaction.user.guild_permissions.administrator
        role_ok = any(r.id == ADMIN_ROLE_ID for r in getattr(interaction.user, "roles", []))
        return role_ok
    return app_commands.check(predicate)

@app_commands.guilds(discord.Object(id=GUILD_ID)) if GUILD_ID else (lambda x: x)
@bot.tree.command(name="관리_상품추가", description="상품을 추가합니다.")
@admin_only()
@app_commands.describe(name="상품명", price="가격(정수)")
async def add_product_cmd(interaction: discord.Interaction, name: str, price: int):
    async with await db() as con:
        try:
            await con.execute("INSERT INTO products(name,price,created_at) VALUES(?,?,?)",
                              (name, price, dt.datetime.utcnow().isoformat()))
            await con.commit()
        except aiosqlite.IntegrityError:
            return await interaction.response.send_message("이미 존재하는 상품명입니다.", ephemeral=True)
    await interaction.response.send_message(f"상품 등록: {name} ({price}원)", ephemeral=True)

@app_commands.guilds(discord.Object(id=GUILD_ID)) if GUILD_ID else (lambda x: x)
@bot.tree.command(name="관리_재고등록", description="재고 코드를 줄바꿈으로 여러 개 등록")
@admin_only()
async def add_stock_cmd(interaction: discord.Interaction, product_id: int, codes: str):
    rows = [c.strip() for c in codes.splitlines() if c.strip()]
    async with await db() as con:
        for c in rows:
            await con.execute("INSERT INTO stock_codes(product_id,code) VALUES(?,?)", (product_id, c))
        await con.commit()
    await interaction.response.send_message(f"재고 {len(rows)}개 등록됨 (상품ID {product_id})", ephemeral=True)

@app_commands.guilds(discord.Object(id=GUILD_ID)) if GUILD_ID else (lambda x: x)
@bot.tree.command(name="관리_핀생성", description="충전핀을 생성합니다.")
@admin_only()
async def create_pin_cmd(interaction: discord.Interaction, pin: str, amount: int):
    async with await db() as con:
        try:
            await con.execute("INSERT INTO topup_pins(pin,amount) VALUES(?,?)", (pin, amount))
            await con.commit()
        except aiosqlite.IntegrityError:
            return await interaction.response.send_message("이미 존재하는 핀입니다.", ephemeral=True)
    await interaction.response.send_message(f"핀 생성: {pin} (+{amount})", ephemeral=True)

@app_commands.guilds(discord.Object(id=GUILD_ID)) if GUILD_ID else (lambda x: x)
@bot.tree.command(name="관리_강제충전", description="특정 유저 잔액 변경(+/-)")
@admin_only()
async def admin_credit_cmd(interaction: discord.Interaction, user: discord.Member, delta: int):
    try:
        new_bal = await change_balance(user.id, delta, "ADMIN", f"by={interaction.user.id}")
    except ValueError:
        return await interaction.response.send_message("잔액 부족/오류", ephemeral=True)
    await interaction.response.send_message(f"{user.display_name} 잔액 변경: {delta} → 현재 {new_bal}", ephemeral=True)

# ============ 라이프사이클 ============

@bot.event
async def on_ready():
    await db_init()
    try:
        if GUILD_ID:
            await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        else:
            await bot.tree.sync()
    except Exception as e:
        print("Sync error:", e)
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("BOT_TOKEN 환경변수를 설정하세요.")
    bot.run(TOKEN)
