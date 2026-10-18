from apscheduler.schedulers.background import BackgroundScheduler

from daily_reset_job import run_daily_reset
from sim_feed import run_sim_feed


def start_scheduler():
    """
    Start the background scheduler. Called explicitly from app.py (guarded
    against Flask's debug reloader so it doesn't start twice).

    Jobs:
      - daily reset at 00:05 IST: roll up yesterday's OCI, reset live counts
      - sim feed every 5 minutes: simulated boardings for routes with no
        real conductor activity, keeping crowding + forecasts live
    """
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

    scheduler.add_job(run_daily_reset, trigger="cron", hour=0, minute=5)
    scheduler.add_job(run_sim_feed, trigger="interval", minutes=5)

    scheduler.start()
    print("⏰ Scheduler started: daily rollup 00:05 IST · sim feed every 5 min", flush=True)

    # Prime the simulation immediately so views are alive on startup
    run_sim_feed()
    return scheduler
