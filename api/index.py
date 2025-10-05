from app import app

# Vercel Serverless Functions 需要这个
application = app

if __name__ == "__main__":
    app.run()