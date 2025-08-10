import discord
from discord.ext import commands
from discord.ui import View, Select, Button
import datetime
import pytz

# ==== 설정 부분 ====
TOKEN = "DISCORD_BOT"
TICKET_CATEGORY_NAME = "⠐ 💳 = 이용하기"
LOG_CHANNEL_ID = 1398267597299912744
ADMIN_ROLE_ID = 123456789012345678
OWNER_ROLE_ID = 987654321098765432
# ==================

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
kst = pytz.timezone('Asia/Seoul')


class CloseTicketButton(Button):
    def __init__(self):
        super().__init__(label="티켓 닫기", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        if interaction.channel.name.startswith("ticket-"):
            await interaction.channel.delete()
            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                now_kst = datetime.datetime.now(kst)
                await log_channel.send(
                    f"티켓 닫힘 | 채널: `{interaction.channel.name}` | 닫은 유저: {interaction.user.mention} | 시간: {now_kst.strftime('%Y-%m-%d %H:%M:%S')}"
                )


class ShopSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="구매하기", description="로블록스 아이템 또는 로벅스 구매", emoji="🛒"),
            discord.SelectOption(label="문의하기", description="문의사항 티켓 열기", emoji="🎫"),
            discord.SelectOption(label="파트너 & 상단배너", description="파트너 또는 상단배너", emoji="👑")
        ]
        super().__init__(placeholder="원하는 항목을 선택하세요", options=options)

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        if not category:
            category = await guild.create_category(TICKET_CATEGORY_NAME)

        ticket_name = f"ticket-{interaction.user.name}"
        existing_channel = discord.utils.get(guild.channels, name=ticket_name)
        if existing_channel:
            await interaction.response.send_message(f"이미 티켓이 존재합니다: {existing_channel.mention}", ephemeral=False)
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

        if admin_role and owner_role:
            mention_embed = discord.Embed(
                title="📩 새 티켓이 생성되었습니다",
                description=f"{admin_role.mention} {owner_role.mention}\n관리자가 곧 응답할 예정입니다.",
                color=discord.Color.green()
            )
            mention_embed.add_field(name="티켓 생성자", value=interaction.user.mention, inline=True)
            mention_embed.add_field(name="생성 시간", value=f"<t:{timestamp_kst}:F>", inline=True)
            mention_embed.set_footer(text="WIND Ticket Bot - 윈드 티켓봇")
            await ticket_channel.send(embed=mention_embed)

        guide_embed = discord.Embed(
            title=f"{self.values[0]} 티켓이 생성되었습니다 🎫",
            description="아래 버튼을 눌러 티켓을 닫을 수 있습니다.",
            color=discord.Color.from_rgb(0, 0, 0)
        )
        guide_embed.add_field(name="생성 시간", value=f"<t:{timestamp_kst}:F>", inline=False)
        guide_embed.set_footer(text=f"WIND Ticket Bot - 윈드 티켓봇 | {now_kst.strftime('%Y-%m-%d %H:%M:%S')}")

        await ticket_channel.send(embed=guide_embed, view=View().add_item(CloseTicketButton()))
        await interaction.response.send_message(f"티켓이 생성되었습니다: {ticket_channel.mention}", ephemeral=False)

        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(
                f"티켓 생성 | 채널: {ticket_channel.mention} | 생성자: {interaction.user.mention} | 항목: `{self.values[0]}` | 시간: {now_kst.strftime('%Y-%m-%d %H:%M:%S')}"
            )


class ShopView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ShopSelect())


@bot.command()
async def 상점(ctx):
    now_kst = datetime.datetime.now(kst)
    embed = discord.Embed(
        title="WIND RBX 상점",
        description="원하는 항목을 아래 드롭다운에서 선택하세요.",
        color=discord.Color.from_rgb(0, 0, 0)
    )
    embed.set_footer(text=f"WIND Ticket Bot - 윈드 티켓봇 | {now_kst.strftime('%Y-%m-%d %H:%M:%S')}")
    await ctx.send(embed=embed, view=ShopView())


bot.run(TOKEN)
