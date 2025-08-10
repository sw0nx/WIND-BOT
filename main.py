import discord
from discord.ext import commands
from discord.ui import View, Select, Button
import datetime
import pytz
from flask import Flask
import threading

# ==== 설정 ====
TOKEN = "TOKEN"
TICKET_CATEGORY_NAME = "⠐ 💳 = 이용하기"
LOG_CHANNEL_ID = 1398267597299912744
ADMIN_ROLE_ID = 123456789012345678
OWNER_ROLE_ID = 987654321098765432
# ==============

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
kst = pytz.timezone('Asia/Seoul')

# ==== Flask 서버 (24시간 유지용) ====
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    threading.Thread(target=run_web).start()
# ==================================


# ====== 버튼 클래스 ======
class CloseTicketButton(Button):
    def __init__(self):
        super().__init__(label="티켓 닫기", style=discord.ButtonStyle.danger, emoji="🔒")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if interaction.channel.name.startswith("ticket-"):
            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            now_kst = datetime.datetime.now(kst)
            if log_channel:
                await log_channel.send(
                    f"🛑 **티켓 닫힘** | 채널: `{interaction.channel.name}` | 닫은 유저: {interaction.user.mention} | 시간: {now_kst.strftime('%Y-%m-%d %H:%M:%S')}"
                )
            await interaction.channel.delete()


# ====== 셀렉트 메뉴 클래스 ======
class ShopSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="구매하기", description="로블록스 아이템 또는 로벅스 구매", emoji="🛒"),
            discord.SelectOption(label="문의하기", description="문의사항 티켓 열기", emoji="🎫"),
            discord.SelectOption(label="파트너 & 상단배너", description="파트너 또는 상단배너 문의", emoji="👑")
        ]
        super().__init__(placeholder="⬇ 원하는 항목을 선택하세요", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME) or await guild.create_category(TICKET_CATEGORY_NAME)

        ticket_name = f"ticket-{interaction.user.name}"
        if discord.utils.get(guild.channels, name=ticket_name):
            await interaction.followup.send(f"⚠ 이미 티켓이 존재합니다: <#{discord.utils.get(guild.channels, name=ticket_name).id}>", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        ticket_channel = await guild.create_text_channel(ticket_name, category=category, overwrites=overwrites)

        admin_role = guild.get_role(ADMIN_ROLE_ID)
        owner_role = guild.get_role(OWNER_ROLE_ID)
        now_kst = datetime.datetime.now(kst)
        timestamp_kst = int(now_kst.timestamp())

        # 알림 임베드
        mention_embed = discord.Embed(
            title="📩 새 티켓 알림",
            description=f"{admin_role.mention if admin_role else ''} {owner_role.mention if owner_role else ''}\n담당자가 곧 응답할 예정입니다.",
            color=discord.Color.dark_grey()
        )
        mention_embed.add_field(name="티켓 생성자", value=interaction.user.mention, inline=True)
        mention_embed.add_field(name="생성 시간", value=f"<t:{timestamp_kst}:F>", inline=True)
        mention_embed.set_footer(text="WIND Ticket Bot")
        await ticket_channel.send(embed=mention_embed)

        # 안내 임베드
        guide_embed = discord.Embed(
            title=f"🎟 {self.values[0]} 티켓 생성됨",
            description="아래 버튼을 눌러 티켓을 닫을 수 있습니다.",
            color=discord.Color.blurple()
        )
        guide_embed.add_field(name="🕒 생성 시간", value=f"<t:{timestamp_kst}:F>", inline=False)
        guide_embed.set_footer(text="WIND Ticket Bot")
        await ticket_channel.send(embed=guide_embed, view=View().add_item(CloseTicketButton()))

        await interaction.followup.send(f"✅ 티켓이 생성되었습니다: {ticket_channel.mention}", ephemeral=True)

        # 로그
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(
                f"📥 **티켓 생성** | 채널: {ticket_channel.mention} | 생성자: {interaction.user.mention} | 항목: `{self.values[0]}` | 시간: {now_kst.strftime('%Y-%m-%d %H:%M:%S')}"
            )


# ====== 뷰 클래스 ======
class ShopView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ShopSelect())


# ====== 명령어 ======
@bot.command()
async def 상점(ctx):
    now_kst = datetime.datetime.now(kst)
    timestamp_kst = int(now_kst.timestamp())

    embed = discord.Embed(
        title="💳 WIND RBX 상점",
        description="아래에서 원하는 항목을 선택하세요.\n━━━━━━━━━━━━━━━━━━━━",
        color=discord.Color.blurple()
    )
    embed.add_field(name="🕒 현재 시간", value=f"<t:{timestamp_kst}:F>", inline=False)
    embed.set_footer(text="WIND Ticket Bot")
    await ctx.send(embed=embed, view=ShopView())


# 실행
keep_alive()
bot.run(TOKEN)
