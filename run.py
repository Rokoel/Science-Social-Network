import eventlet, sys
eventlet.monkey_patch()

from app import create_app, socketio

use_redis = '--no-redis' not in sys.argv

app = create_app(use_redis=use_redis)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug='--debug' in sys.argv)
