import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Select
from datetime import datetime
import psycopg2
import os
from dotenv import load_dotenv

# ================= ENV =================
load_dotenv()

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# ================= DB HELPER =================
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    return conn, cursor

# ================= ROLE HELPERS =================
def get_user_role(user_id: int) -> str:
    conn, cursor = get_db()
    cursor.execute(
        "SELECT role FROM user_roles WHERE user_id=%s",
        (user_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "user"

def is_admin(user_id: int) -> bool:
    return get_user_role(user_id) in ("admin", "superuser")

def log_admin_action(admin_id: int, action: str, target: str):
    conn, cursor = get_db()
    cursor.execute(
        "INSERT INTO admin_logs (admin_id, action, target, timestamp) VALUES (%s, %s, %s, %s)",
        (admin_id, action, target, datetime.now())
    )
    conn.commit()
    conn.close()

# ================= BOT SETUP =================
intents = discord.Intents.default()
intents.message_content = True

class NOYDBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Slash commands synced")

bot = NOYDBot()

@bot.event
async def on_ready():
    SUPERUSER_ID = 123456789012345678  # 🔴 PUT YOUR DISCORD USER ID

    conn, cursor = get_db()
    cursor.execute(
        "INSERT INTO user_roles (user_id, role) VALUES (%s, %s) "
        "ON CONFLICT (user_id) DO NOTHING",
        (SUPERUSER_ID, "superuser")
    )
    conn.commit()
    conn.close()

    print(f"🚀 NOYD Task Bot online as {bot.user}")

# ================= UI COMPONENTS =================

class TaskActionView(View):
    def __init__(self, task_id, status, user_id):
        super().__init__(timeout=60)
        self.add_item(StartButton(task_id, status, user_id))
        self.add_item(DoneButton(task_id, status, user_id))

class StartButton(Button):
    def __init__(self, task_id, status, user_id):
        super().__init__(label="▶ Start", style=discord.ButtonStyle.primary)
        self.task_id = task_id
        self.status = status
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⛔ Not your task.", ephemeral=True)
            return

        new_status = "in_progress" if self.status != "in_progress" else "todo"

        conn, cursor = get_db()
        cursor.execute(
            "UPDATE tasks SET status=%s WHERE id=%s",
            (new_status, self.task_id)
        )
        conn.commit()
        conn.close()

        await interaction.response.send_message(
            f"🔄 Task #{self.task_id} → **{new_status.upper()}**",
            ephemeral=True
        )

class DoneButton(Button):
    def __init__(self, task_id, status, user_id):
        super().__init__(label="✅ Done", style=discord.ButtonStyle.success)
        self.task_id = task_id
        self.status = status
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⛔ Not your task.", ephemeral=True)
            return

        new_status = "done" if self.status != "done" else "todo"

        conn, cursor = get_db()
        cursor.execute(
            "UPDATE tasks SET status=%s, completed_at=%s WHERE id=%s",
            (new_status, datetime.now() if new_status == "done" else None, self.task_id)
        )
        conn.commit()
        conn.close()

        await interaction.response.send_message(
            f"🎉 Task #{self.task_id} → **{new_status.upper()}**",
            ephemeral=True
        )

class TaskSelect(Select):
    def __init__(self, tasks, user_id):
        options = [
            discord.SelectOption(
                label=f"#{task_id} — {title}",
                description=f"Status: {status.upper()}",
                value=str(task_id)
            )
            for task_id, title, status in tasks
        ]

        super().__init__(
            placeholder="Select a task to manage",
            options=options
        )
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⛔ Not your task list.", ephemeral=True)
            return

        task_id = int(self.values[0])

        conn, cursor = get_db()
        cursor.execute("SELECT status FROM tasks WHERE id=%s", (task_id,))
        status = cursor.fetchone()[0]
        conn.close()

        await interaction.response.send_message(
            f"🛠️ Manage Task #{task_id}",
            view=TaskActionView(task_id, status, self.user_id),
            ephemeral=True
        )

class TaskSelectView(View):
    def __init__(self, tasks, user_id):
        super().__init__(timeout=120)
        self.add_item(TaskSelect(tasks, user_id))

# ================= COMMANDS =================

@bot.tree.command(name="task_create", description="Create a new task")
@app_commands.describe(title="Task title", member="Assign task to user")
async def task_create(interaction: discord.Interaction, title: str, member: discord.Member):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("⛔ Admin access required.", ephemeral=True)
        return

    conn, cursor = get_db()
    cursor.execute(
        "INSERT INTO tasks (title, assigned_to, created_by, status, created_at) "
        "VALUES (%s, %s, %s, %s, %s)",
        (title, member.id, interaction.user.id, "todo", datetime.now())
    )
    conn.commit()
    conn.close()

    await interaction.response.send_message(
        f"📝 Task **{title}** assigned to {member.mention}"
    )

@bot.tree.command(name="my_tasks", description="View and manage your tasks")
async def my_tasks(interaction: discord.Interaction):
    conn, cursor = get_db()
    cursor.execute(
        "SELECT id, title, status FROM tasks WHERE assigned_to=%s",
        (interaction.user.id,)
    )
    tasks = cursor.fetchall()
    conn.close()

    if not tasks:
        await interaction.response.send_message("📭 You have no tasks.")
        return

    embed = discord.Embed(
        title="🗂️ Your Tasks",
        description="Select a task below to manage it",
        color=discord.Color.blue()
    )

    for task_id, title, status in tasks:
        embed.add_field(
            name=f"#{task_id} — {title}",
            value=f"Status: **{status.upper()}**",
            inline=False
        )

    await interaction.response.send_message(
        embed=embed,
        view=TaskSelectView(tasks, interaction.user.id)
    )

@bot.tree.command(name="task_delete", description="Delete a task (ADMIN ONLY)")
@app_commands.describe(task_id="Task ID", confirm="Type DELETE to confirm")
async def task_delete(interaction: discord.Interaction, task_id: int, confirm: str):
    await interaction.response.defer(ephemeral=True)

    if not is_admin(interaction.user.id):
        await interaction.followup.send("⛔ Admin access required.")
        return

    if confirm != "DELETE":
        await interaction.followup.send("❌ Type DELETE exactly to confirm.")
        return

    conn, cursor = get_db()
    cursor.execute("SELECT title FROM tasks WHERE id=%s", (task_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        await interaction.followup.send("❌ Task not found.")
        return

    cursor.execute("DELETE FROM tasks WHERE id=%s", (task_id,))
    conn.commit()
    conn.close()

    log_admin_action(interaction.user.id, "DELETE_TASK", f"Task #{task_id}")

    await interaction.followup.send(f"🗑️ Task #{task_id} deleted.")

# ================= ROLE / INFO COMMANDS =================

@bot.tree.command(name="grant_admin", description="Grant admin rights (SUPERUSER ONLY)")
@app_commands.describe(member="User to grant admin rights")
async def grant_admin(interaction: discord.Interaction, member: discord.Member):
    if get_user_role(interaction.user.id) != "superuser":
        await interaction.response.send_message("⛔ Only superuser can grant admin.", ephemeral=True)
        return

    conn, cursor = get_db()
    cursor.execute(
        "INSERT INTO user_roles (user_id, role) VALUES (%s, %s) "
        "ON CONFLICT (user_id) DO UPDATE SET role='admin'",
        (member.id, "admin")
    )
    conn.commit()
    conn.close()

    log_admin_action(interaction.user.id, "GRANT_ADMIN", member.name)
    await interaction.response.send_message(f"✅ {member.mention} is now an **ADMIN**")

@bot.tree.command(name="revoke_admin", description="Revoke admin rights (SUPERUSER ONLY)")
@app_commands.describe(member="Admin to revoke")
async def revoke_admin(interaction: discord.Interaction, member: discord.Member):
    if get_user_role(interaction.user.id) != "superuser":
        await interaction.response.send_message("⛔ Only superuser can revoke admin.", ephemeral=True)
        return

    conn, cursor = get_db()
    cursor.execute(
        "DELETE FROM user_roles WHERE user_id=%s AND role='admin'",
        (member.id,)
    )
    conn.commit()
    conn.close()

    log_admin_action(interaction.user.id, "REVOKE_ADMIN", member.name)
    await interaction.response.send_message(f"🔻 {member.mention} is no longer an admin")

@bot.tree.command(name="myrole", description="Show your role")
async def myrole(interaction: discord.Interaction):
    role = get_user_role(interaction.user.id)

    embed = discord.Embed(
        title="🔐 Your Role",
        description=f"You are **{role.upper()}**",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="whoissuper", description="Show the superuser")
async def whoissuper(interaction: discord.Interaction):
    conn, cursor = get_db()
    cursor.execute("SELECT user_id FROM user_roles WHERE role='superuser'")
    row = cursor.fetchone()
    conn.close()

    if not row:
        await interaction.response.send_message("❌ No superuser found.")
        return

    user = await bot.fetch_user(row[0])

    embed = discord.Embed(
        title="👑 Superuser",
        description=user.name,
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=user.display_avatar.url)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="whoisadmin", description="Show admins")
async def whoisadmin(interaction: discord.Interaction):
    conn, cursor = get_db()
    cursor.execute("SELECT user_id FROM user_roles WHERE role='admin'")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await interaction.response.send_message("ℹ️ No admins.")
        return

    admins = [await bot.fetch_user(r[0]) for r in rows]

    if len(admins) == 1:
        admin = admins[0]
        embed = discord.Embed(
            title="🛡️ Admin",
            description=admin.name,
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=admin.display_avatar.url)
    else:
        embed = discord.Embed(
            title="🛡️ Admins",
            description="\n".join(f"• {a.name}" for a in admins),
            color=discord.Color.blue()
        )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="admin_logs", description="View admin logs")
async def admin_logs(interaction: discord.Interaction):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("⛔ Admin access required.", ephemeral=True)
        return

    conn, cursor = get_db()
    cursor.execute(
        "SELECT admin_id, action, target, timestamp FROM admin_logs ORDER BY id DESC LIMIT 10"
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await interaction.response.send_message("ℹ️ No logs found.")
        return

    text = ""
    for admin_id, action, target, ts in rows:
        admin = await bot.fetch_user(admin_id)
        text += f"• **{admin.name}** → `{action}` → {target}\n"

    embed = discord.Embed(
        title="📜 Admin Logs",
        description=text,
        color=discord.Color.orange()
    )

    await interaction.response.send_message(embed=embed)

# ================= RUN =================
bot.run(TOKEN)
