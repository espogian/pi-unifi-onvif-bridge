import socket
import struct
import uuid
import datetime
import netifaces
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from xml.etree import ElementTree as ET

logger = logging.getLogger('OnvifServer')

def get_ip_address_from_mac(mac_address):
    mac_address = mac_address.lower()
    for iface in netifaces.interfaces():
        addrs = netifaces.ifaddresses(iface)
        if netifaces.AF_LINK in addrs:
            for link in addrs[netifaces.AF_LINK]:
                if link['addr'].lower() == mac_address:
                    if netifaces.AF_INET in addrs:
                        return addrs[netifaces.AF_INET][0]['addr']
    return None

class OnvifHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(format % args)

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        # Determine service and action
        action = "Unknown"
        # Very basic XML parsing to find body content
        try:
            root = ET.fromstring(post_data)
            # Namespaces are annoying in ElementTree, ignore for simple routing
            body = root.find('.//{http://www.w3.org/2003/05/soap-envelope}Body')
            if body is not None and len(body) > 0:
                action = body[0].tag.split('}')[-1]
        except:
            pass

        response_xml = self.server.onvif_instance.handle_request(self.path, action, post_data)
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/soap+xml; charset=utf-8')
        self.end_headers()
        self.wfile.write(response_xml.encode('utf-8'))

    def do_GET(self):
        if self.path == '/snapshot.png':
            try:
                with open('./resources/snapshot.png', 'rb') as f:
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/png')
                    self.end_headers()
                    self.wfile.write(f.read())
            except FileNotFoundError:
                self.send_error(404, "Snapshot not found")
        else:
            self.send_error(404)

class OnvifServerInstance:
    def __init__(self, config):
        self.config = config
        self.uuid = config['uuid']
        if not self.config.get('hostname'):
            self.config['hostname'] = get_ip_address_from_mac(self.config['mac'])
        
        self.setup_profiles()

    def setup_profiles(self):
        # Construct profile objects similar to Node version
        self.profiles = []
        # Main Stream
        self.profiles.append(self._create_profile('MainStream', 'main_stream', self.config['highQuality'], 'encoder_hq'))
        # Sub Stream
        if self.config.get('lowQuality'):
            self.profiles.append(self._create_profile('SubStream', 'sub_stream', self.config['lowQuality'], 'encoder_lq'))

    def _create_profile(self, name, token, conf, enc_token):
        return {
            'Name': name,
            'token': token,
            'width': conf['width'],
            'height': conf['height'],
            'framerate': conf['framerate'],
            'bitrate': conf['bitrate'],
            'enc_token': enc_token
        }

    def handle_request(self, path, action, body):
        logger.debug(f"Request: {path} Action: {action}")
        
        if action == 'GetSystemDateAndTime':
            return self.resp_get_system_date_and_time()
        elif action == 'GetCapabilities':
            return self.resp_get_capabilities()
        elif action == 'GetServices':
            return self.resp_get_services()
        elif action == 'GetDeviceInformation':
            return self.resp_get_device_information()
        elif action == 'GetProfiles':
            return self.resp_get_profiles()
        elif action == 'GetVideoSources':
            return self.resp_get_video_sources()
        elif action == 'GetSnapshotUri':
            return self.resp_get_snapshot_uri(body)
        elif action == 'GetStreamUri':
            return self.resp_get_stream_uri(body)
        
        return self.wrap_soap("")

    def wrap_soap(self, content):
        return f"""<?xml version="1.0" encoding="UTF-8"?>
        <s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
            <s:Body>{content}</s:Body>
        </s:Envelope>"""

    # --- SOAP Responses ---
    
    def resp_get_system_date_and_time(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        return self.wrap_soap(f"""
            <tds:GetSystemDateAndTimeResponse>
                <tds:SystemDateAndTime>
                    <tt:DateTimeType>NTP</tt:DateTimeType>
                    <tt:DaylightSavings>false</tt:DaylightSavings>
                    <tt:TimeZone><tt:TZ>UTC+00:00</tt:TZ></tt:TimeZone>
                    <tt:UTCDateTime>
                        <tt:Time><tt:Hour>{now.hour}</tt:Hour><tt:Minute>{now.minute}</tt:Minute><tt:Second>{now.second}</tt:Second></tt:Time>
                        <tt:Date><tt:Year>{now.year}</tt:Year><tt:Month>{now.month}</tt:Month><tt:Day>{now.day}</tt:Day></tt:Date>
                    </tt:UTCDateTime>
                </tds:SystemDateAndTime>
            </tds:GetSystemDateAndTimeResponse>
        """)

    def resp_get_capabilities(self):
        base_url = f"http://{self.config['hostname']}:{self.config['ports']['server']}/onvif"
        return self.wrap_soap(f"""
            <tds:GetCapabilitiesResponse>
                <tds:Capabilities>
                    <tt:Device>
                        <tt:XAddr>{base_url}/device_service</tt:XAddr>
                        <tt:Network><tt:IPFilter>false</tt:IPFilter><tt:ZeroConfiguration>false</tt:ZeroConfiguration><tt:IPVersion6>false</tt:IPVersion6><tt:DynDNS>false</tt:DynDNS></tt:Network>
                        <tt:System><tt:DiscoveryResolve>false</tt:DiscoveryResolve><tt:DiscoveryBye>false</tt:DiscoveryBye><tt:RemoteDiscovery>false</tt:RemoteDiscovery><tt:SupportedVersions><tt:Major>2</tt:Major><tt:Minor>5</tt:Minor></tt:SupportedVersions></tt:System>
                    </tt:Device>
                    <tt:Media>
                        <tt:XAddr>{base_url}/media_service</tt:XAddr>
                        <tt:StreamingCapabilities><tt:RTPMulticast>false</tt:RTPMulticast><tt:RTP_TCP>true</tt:RTP_TCP><tt:RTP_RTSP_TCP>true</tt:RTP_RTSP_TCP></tt:StreamingCapabilities>
                    </tt:Media>
                </tds:Capabilities>
            </tds:GetCapabilitiesResponse>
        """)

    def resp_get_services(self):
        base_url = f"http://{self.config['hostname']}:{self.config['ports']['server']}/onvif"
        return self.wrap_soap(f"""
            <tds:GetServicesResponse>
                <tds:Service>
                    <tds:Namespace>http://www.onvif.org/ver10/device/wsdl</tds:Namespace>
                    <tds:XAddr>{base_url}/device_service</tds:XAddr>
                    <tds:Version><tt:Major>2</tt:Major><tt:Minor>5</tt:Minor></tds:Version>
                </tds:Service>
                <tds:Service>
                    <tds:Namespace>http://www.onvif.org/ver10/media/wsdl</tds:Namespace>
                    <tds:XAddr>{base_url}/media_service</tds:XAddr>
                    <tds:Version><tt:Major>2</tt:Major><tt:Minor>5</tt:Minor></tds:Version>
                </tds:Service>
            </tds:GetServicesResponse>
        """)

    def resp_get_device_information(self):
        return self.wrap_soap(f"""
            <tds:GetDeviceInformationResponse>
                <tds:Manufacturer>Raspberry Pi Holdings PLC</tds:Manufacturer>
                <tds:Model>Raspberry Pi Python</tds:Model>
                <tds:FirmwareVersion>1.0.0</tds:FirmwareVersion>
                <tds:SerialNumber>{self.config['name'].replace(' ', '_')}-0000</tds:SerialNumber>
                <tds:HardwareId>{self.config['name'].replace(' ', '_')}-1001</tds:HardwareId>
            </tds:GetDeviceInformationResponse>
        """)

    def resp_get_profiles(self):
        profiles_xml = ""
        for p in self.profiles:
            profiles_xml += f"""
                <trt:Profiles token="{p['token']}">
                    <tt:Name>{p['Name']}</tt:Name>
                    <tt:VideoSourceConfiguration token="video_src_config_token">
                        <tt:Name>VideoSource</tt:Name>
                        <tt:UseCount>2</tt:UseCount>
                        <tt:SourceToken>video_src_token</tt:SourceToken>
                        <tt:Bounds x="0" y="0" width="{p['width']}" height="{p['height']}"/>
                    </tt:VideoSourceConfiguration>
                    <tt:VideoEncoderConfiguration token="{p['enc_token']}">
                        <tt:Name>PiCameraConfig</tt:Name>
                        <tt:UseCount>1</tt:UseCount>
                        <tt:Encoding>H264</tt:Encoding>
                        <tt:Resolution><tt:Width>{p['width']}</tt:Width><tt:Height>{p['height']}</tt:Height></tt:Resolution>
                        <tt:RateControl><tt:FrameRateLimit>{p['framerate']}</tt:FrameRateLimit><tt:EncodingInterval>1</tt:EncodingInterval><tt:BitrateLimit>{p['bitrate']}</tt:BitrateLimit></tt:RateControl>
                    </tt:VideoEncoderConfiguration>
                </trt:Profiles>
            """
        return self.wrap_soap(f"<trt:GetProfilesResponse>{profiles_xml}</trt:GetProfilesResponse>")

    def resp_get_video_sources(self):
        hq = self.config['highQuality']
        return self.wrap_soap(f"""
            <trt:GetVideoSourcesResponse>
                <trt:VideoSources token="video_src_token">
                    <tt:Framerate>{hq['framerate']}</tt:Framerate>
                    <tt:Resolution><tt:Width>{hq['width']}</tt:Width><tt:Height>{hq['height']}</tt:Height></tt:Resolution>
                </trt:VideoSources>
            </trt:GetVideoSourcesResponse>
        """)

    def resp_get_snapshot_uri(self, body):
        # Basic parsing to check for sub_stream
        uri = f"http://{self.config['hostname']}:{self.config['ports']['server']}/snapshot.png"
        if 'sub_stream' in body and self.config.get('lowQuality') and self.config['lowQuality'].get('snapshot'):
             uri = f"http://{self.config['hostname']}:{self.config['ports']['snapshot']}{self.config['lowQuality']['snapshot']}"
        elif self.config['highQuality'].get('snapshot'):
             uri = f"http://{self.config['hostname']}:{self.config['ports']['snapshot']}{self.config['highQuality']['snapshot']}"
             
        return self.wrap_soap(f"""
            <trt:GetSnapshotUriResponse>
                <trt:MediaUri>
                    <tt:Uri>{uri}</tt:Uri>
                    <tt:InvalidAfterConnect>false</tt:InvalidAfterConnect>
                    <tt:InvalidAfterReboot>false</tt:InvalidAfterReboot>
                    <tt:Timeout>PT30S</tt:Timeout>
                </trt:MediaUri>
            </trt:GetSnapshotUriResponse>
        """)

    def resp_get_stream_uri(self, body):
        path = self.config['highQuality']['rtsp']
        if 'sub_stream' in body and self.config.get('lowQuality'):
            path = self.config['lowQuality']['rtsp']
            
        uri = f"rtsp://{self.config['hostname']}:{self.config['ports']['rtsp']}{path}"
        
        return self.wrap_soap(f"""
            <trt:GetStreamUriResponse>
                <trt:MediaUri>
                    <tt:Uri>{uri}</tt:Uri>
                    <tt:InvalidAfterConnect>false</tt:InvalidAfterConnect>
                    <tt:InvalidAfterReboot>false</tt:InvalidAfterReboot>
                    <tt:Timeout>PT30S</tt:Timeout>
                </trt:MediaUri>
            </trt:GetStreamUriResponse>
        """)

# --- Discovery Class ---
class WSDiscovery:
    def __init__(self, config):
        self.config = config
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
    def start(self):
        # Bind to all interfaces on 3702
        self.sock.bind(('', 3702))
        
        # Add membership to multicast group
        mreq = struct.pack("4sl", socket.inet_aton('239.255.255.250'), socket.INADDR_ANY)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        
        while True:
            try:
                data, addr = self.sock.recvfrom(4096)
                if b'Probe' in data and b'NetworkVideoTransmitter' in data:
                    self.send_probe_match(data, addr)
            except Exception as e:
                logger.error(f"Discovery error: {e}")

    def send_probe_match(self, data, addr):
        # Extract RelatesTo/MessageID logic omitted for brevity, using generic match
        # In a robust app, extract the MessageID from 'data' to use as RelatesTo
        msg_uuid = uuid.uuid4()
        
        response = f"""<?xml version="1.0" encoding="UTF-8"?>
        <SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
            <SOAP-ENV:Header>
                <wsa:MessageID>uuid:{msg_uuid}</wsa:MessageID>
                <wsa:RelatesTo>uuid:{self.config['uuid']}</wsa:RelatesTo>
                <wsa:To SOAP-ENV:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</wsa:To>
                <wsa:Action SOAP-ENV:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</wsa:Action>
            </SOAP-ENV:Header>
            <SOAP-ENV:Body>
                <d:ProbeMatches>
                    <d:ProbeMatch>
                        <wsa:EndpointReference><wsa:Address>urn:uuid:{self.config['uuid']}</wsa:Address></wsa:EndpointReference>
                        <d:Types>dn:NetworkVideoTransmitter</d:Types>
                        <d:Scopes>onvif://www.onvif.org/type/video_encoder onvif://www.onvif.org/name/{self.config['name']}</d:Scopes>
                        <d:XAddrs>http://{self.config['hostname']}:{self.config['ports']['server']}/onvif/device_service</d:XAddrs>
                        <d:MetadataVersion>1</d:MetadataVersion>
                    </d:ProbeMatch>
                </d:ProbeMatches>
            </SOAP-ENV:Body>
        </SOAP-ENV:Envelope>"""
        
        self.sock.sendto(response.encode('utf-8'), addr)