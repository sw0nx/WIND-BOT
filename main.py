import discord
from discord.ext import commands
from discord import app_commands

TOKEN = os.getenv("BOT_TOKEN")
GUILD_ID = 1398256208887939214
CATEGORY_ID = 1398263224062836829
ADMIN_ROLE_ID = 123456789012345678

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="문의"),
            discord.SelectOption(label="신고"),
            discord.SelectOption(label="기타"),
        ]
        super().__init__(placeholder="티켓 항목 선택", options=options)

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, id=CATEGORY_ID)
        admin_role = guild.get_role(ADMIN_ROLE_ID)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True),
            admin_role: discord.PermissionOverwrite(view_channel=True)
        }

        channel = await guild.create_text_channel(
            name=f"{self.values[0]}-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )

        await interaction.response.send_message(f"티켓이 생성되었습니다: {channel.mention}", ephemeral=True)
        await channel.send(f"{interaction.user.mention} 님이 티켓을 생성했습니다.")

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

@bot.tree.command(name="티켓", description="티켓 생성")
async def ticket_cmd(interaction: discord.Interaction):
    view = TicketView()
    # 3초 안에 응답
    await interaction.response.send_message("아래에서 선택하세요.", view=view)

@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"✅ 로그인됨: {bot.user}")

bot.run(TOKEN)
