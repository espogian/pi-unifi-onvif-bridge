import argparse
import sys
import yaml
import threading
import socket
import logging
import asyncio
from http.server import HTTPServer

# Import local modules
from src.config_builder import create_config
from src.onvif_server import OnvifServerInstance, OnvifHandler, WSDiscovery

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('Main')

class TCPProxy(threading.Thread):
    def __init__(self, src_port, dst_host, dst_port):
        super().__init__()
        self.src_port = src_port
        self.dst_host = dst_host
        self.dst_port = dst_port
        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def run(self):
        try:
            self.server_socket.bind(('0.0.0.0', self.src_port))
            self.server_socket.listen(5)
            logger.info(f"TCP Proxy started: Local :{self.src_port} -> {self.dst_host}:{self.dst_port}")
            while self.running:
                client_sock, _ = self.server_socket.accept()
                threading.Thread(target=self.handle_client, args=(client_sock,)).start()
        except Exception as e:
            logger.error(f"Proxy error on port {self.src_port}: {e}")

    def handle_client(self, client_sock):
        remote_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            remote_sock.connect((self.dst_host, self.dst_port))
            self.pipe_sockets(client_sock, remote_sock)
        except Exception as e:
            # Only log debug to prevent spam if camera is temporarily unreachable
            logger.debug(f"Connection failed: {e}")
            client_sock.close()

    def pipe_sockets(self, sock1, sock2):
        def forward(source, destination):
            try:
                while True:
                    data = source.recv(4096)
                    if not data: break
                    destination.sendall(data)
            except:
                pass
            finally:
                try: destination.shutdown(socket.SHUT_RDWR) 
                except: pass
                try: destination.close() 
                except: pass

        t1 = threading.Thread(target=forward, args=(sock1, sock2))
        t2 = threading.Thread(target=forward, args=(sock2, sock1))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

def main():
    parser = argparse.ArgumentParser(description='Virtual Onvif Server (Python)')
    parser.add_argument('-cc', '--create-config', action='store_true', help='create a new config')
    parser.add_argument('-d', '--debug', action='store_true', help='show debug info')
    parser.add_argument('config', nargs='?', help='config filename')

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.create_config:
        hostname = input('Onvif Server: ')
        username = input('Onvif Username: ')
        password = input('Onvif Password: ')
        
        print('Generating config ...')
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            config = loop.run_until_complete(create_config(hostname, username, password))
            print('# ==================== CONFIG START ====================')
            print(yaml.dump(config, sort_keys=False))
            print('# ===================== CONFIG END =====================')
        except Exception as e:
            print(f"Error creating config: {e}")
        return

    if not args.config:
        logger.error('Please specify a config filename!')
        sys.exit(1)

    try:
        with open(args.config, 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to read config: {e}")
        sys.exit(1)

    proxies_to_start = {}

    for onvif_conf in config['onvif']:
        # 1. Start HTTP SOAP Server
        server_instance = OnvifServerInstance(onvif_conf)
        
        if not server_instance.config['hostname']:
            logger.error(f"Could not determine IP for MAC {onvif_conf['mac']}")
            continue

        # --- FIX START ---
        # Initialize the HTTPServer with the generic OnvifHandler
        httpd = HTTPServer((server_instance.config['hostname'], onvif_conf['ports']['server']), OnvifHandler)
        
        # Attach the specific ONVIF instance logic to the SERVER object
        # This allows self.server.onvif_instance to work in the handler
        httpd.onvif_instance = server_instance
        # --- FIX END ---
        
        t_server = threading.Thread(target=httpd.serve_forever)
        t_server.daemon = True
        t_server.start()
        logger.info(f"Started ONVIF Server for {onvif_conf['name']} at {server_instance.config['hostname']}:{onvif_conf['ports']['server']}")

        # 2. Start Discovery
        discovery = WSDiscovery(server_instance.config)
        t_discovery = threading.Thread(target=discovery.start)
        t_discovery.daemon = True
        t_discovery.start()

        # 3. Prepare Proxies
        target = onvif_conf['target']
        if onvif_conf['ports'].get('rtsp') and target['ports'].get('rtsp'):
            key = (onvif_conf['ports']['rtsp'], target['hostname'], target['ports']['rtsp'])
            proxies_to_start[key] = True
        
        if onvif_conf['ports'].get('snapshot') and target['ports'].get('snapshot'):
            key = (onvif_conf['ports']['snapshot'], target['hostname'], target['ports']['snapshot'])
            proxies_to_start[key] = True

    # Start TCP Proxies
    for (src_port, dst_host, dst_port) in proxies_to_start:
        p = TCPProxy(src_port, dst_host, dst_port)
        p.daemon = True
        p.start()

    # Keep main thread alive
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping...")

if __name__ == '__main__':
    main()