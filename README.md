# Installation Instructions
## Windows Installation
### Prerequisites
- Python 3.8.10 or higher
- Git
- Internet connection
### Step 1: Clone the Repository
```text
git clone https://github.com/Rokoel/Science-Social-Network.git
cd Science-Social-Network
```
### Step 2: Set Up Virtual Environment
```text
python -m venv venv
venv\Scripts\activate
```
### Step 3: Install Dependencies
```text
pip install -r requirements.txt
```

### Step 4: Initialize the Application
```text
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"
```
### Step 5: Run the Application Without Redis
Open a new Command Prompt window, navigate to the project folder, activate the virtual environment, and run:

```text
venv\Scripts\activate
python run.py --no-redis
```

The application will be accessible at http://localhost:5000 in your web browser.

## Linux Installation
### Prerequisites
- Python 3.7 or higher
- Git
- pip
### Step 1: Clone the Repository
```bash
git clone https://github.com/Rokoel/Science-Social-Network.git
cd Science-Social-Network
```
### Step 2: Set Up Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```
### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```
### Step 4: Set Up Redis
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install redis-server
sudo systemctl start redis-server

# For CentOS/RHEL
sudo yum install redis
sudo systemctl start redis

# Verify Redis is running
redis-cli ping
# Should return PONG
```
### Step 5: Initialize the Application
```bash
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"
```
### Step 6: Run the Application
```bash
python run.py
# if running without redis:
python run.py --no-redis
```
The application will be accessible at http://localhost:5000 in your web browser.

# Troubleshooting
## Common Issues
### Redis Connection Error:
Ensure Redis server is running
Check that it's running on the default port (6379)

### Package Installation Errors:
Try updating pip: `pip install --upgrade pip`
Install packages individually if there are conflicts

### Database Errors:
Delete the `app.db` file and reinitialize if database schema errors occur

### File Upload Issues:
Ensure the app/static/uploads directory exists and is writable
