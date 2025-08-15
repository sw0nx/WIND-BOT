import os
import discord
from discord import app_commands
from discord.ext import commands

# 환경변수에서 토큰 불러오기
TOKEN = os.getenv("BOT_TOKEN")  
GUILD_ID = 1398256208887939214  # 서버 ID
CATEGORY_ID = 1398263224062836829  # 티켓 카테고리 ID
ADMIN_ROLE_ID = 1398268476933542018  # 관리자 역할 ID

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True  # 디버그용

bot = commands.Bot(command_prefix="!", intents=intents)

class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="문의", description="문의 티켓을 엽니다."),
            discord.SelectOption(label="신고", description="신고 티켓을 엽니다."),
            discord.SelectOption(label="기타", description="기타 티켓을 엽니다."),
        ]
        super().__init__(
            placeholder="티켓 항목 선택",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, id=CATEGORY_ID)
        admin_role = guild.get_role(ADMIN_ROLE_ID)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            admin_role: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        channel = await guild.create_text_channel(
            name=f"{self.values[0]}-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )

        await interaction.response.send_message(f"✅ 티켓이 생성되었습니다: {channel.mention}", ephemeral=True)
        await channel.send(f"{interaction.user.mention} 님이 **{self.values[0]}** 티켓을 생성했습니다.")

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

@bot.tree.command(name="티켓", description="티켓 생성 메뉴를 표시합니다.")
async def ticket_command(interaction: discord.Interaction):
    embed = discord.Embed(
        description="아래 드롭다운중 하나를 선택해 티켓을 열어주세요.\n\n티켓에서 맨션시 티켓답니다",
        color=0x2B2D31
    )
    await interaction.response.send_message(embed=embed, view=TicketView())

@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"✅ 로그인됨: {bot.user}")

if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("❌ BOT_TOKEN 환경변수가 설정되지 않았습니다.")
    bot.run(TOKEN)
