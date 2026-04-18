from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from app.models import Task, db

def start_scheduler(app):
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=lambda: execute_task_check(app),
        trigger="interval",
        minutes=30,  # Check every 30 min, not every 60 seconds
        id='task_escalation',
        replace_existing=True
    )
    scheduler.start()
    print("[Scheduler] Task escalation job started (every 30 min).")

def execute_task_check(app):
    with app.app_context():
        try:
            now = datetime.utcnow()
            # Only escalate tasks that have been pending for > 24 hours
            cutoff = now - timedelta(hours=24)
            pending_tasks = Task.query.filter(
                Task.status == 'pending',
                Task.created_at <= cutoff
            ).all()

            escalated = 0
            for t in pending_tasks:
                if t.priority == 'low':
                    t.priority = 'medium'
                    escalated += 1
                elif t.priority == 'medium':
                    t.priority = 'high'
                    escalated += 1
                # Already 'high' — don't touch it

            if escalated:
                db.session.commit()
                print(f"[Scheduler] Escalated {escalated} task(s) at {now.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                print(f"[Scheduler] No tasks to escalate at {now.strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as e:
            print(f"[Scheduler] ERROR during task escalation: {e}")
            try:
                db.session.rollback()
            except Exception:
                pass

