from app import create_app, db
from app.services.scheduler import start_scheduler

app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    start_scheduler(app)
    app.run(debug=True, host='0.0.0.0', port=5000)
