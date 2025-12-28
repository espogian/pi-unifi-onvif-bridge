import uuid
from onvif import ONVIFCamera
from urllib.parse import urlparse

def extract_path(url):
    parsed = urlparse(url)
    return parsed.path

async def create_config(hostname, username, password):
    # Determine port
    port = 80
    host_clean = hostname
    if ':' in hostname:
        parts = hostname.split(':')
        host_clean = parts[0]
        port = int(parts[1])

    # Connect to Camera
    my_cam = ONVIFCamera(host_clean, port, username, password)
    media_service = my_cam.create_media_service()
    
    profiles = media_service.GetProfiles()
    
    cameras = {}
    
    for profile in profiles:
        video_source = profile.VideoSourceConfiguration.SourceToken
        
        if video_source not in cameras:
            cameras[video_source] = []

        # Get Snapshot URI
        snapshot_resp = media_service.GetSnapshotUri({'ProfileToken': profile.token})
        
        # Get Stream URI
        stream_setup = {'Stream': 'RTP-Unicast', 'Transport': {'Protocol': 'RTSP'}}
        stream_resp = media_service.GetStreamUri({'StreamSetup': stream_setup, 'ProfileToken': profile.token})

        # Inject into profile object for later processing
        profile.streamUri = stream_resp.Uri
        profile.snapshotUri = snapshot_resp.Uri
        cameras[video_source].append(profile)

    config = {'onvif': []}
    server_port = 8081

    for source_token, profile_list in cameras.items():
        if not profile_list:
            continue
            
        # Logic to find Main (High) and Sub (Low) streams
        main_stream = profile_list[0]
        sub_stream = profile_list[1] if len(profile_list) > 1 else profile_list[0]

        swap_streams = False
        mq = main_stream.VideoEncoderConfiguration.Quality
        sq = sub_stream.VideoEncoderConfiguration.Quality
        
        if sq > mq:
            swap_streams = True
        elif sq == mq:
            mw = main_stream.VideoEncoderConfiguration.Resolution.Width
            sw = sub_stream.VideoEncoderConfiguration.Resolution.Width
            if sw > mw:
                swap_streams = True
        
        if swap_streams:
            main_stream, sub_stream = sub_stream, main_stream

        camera_config = {
            'mac': '<ONVIF PROXY MAC ADDRESS HERE>',
            'ports': {
                'server': server_port,
                'rtsp': 8554,
                'snapshot': 8580
            },
            'name': main_stream.VideoSourceConfiguration.Name,
            'uuid': str(uuid.uuid4()),
            'highQuality': {
                'rtsp': extract_path(main_stream.streamUri),
                'snapshot': extract_path(main_stream.snapshotUri),
                'width': main_stream.VideoEncoderConfiguration.Resolution.Width,
                'height': main_stream.VideoEncoderConfiguration.Resolution.Height,
                'framerate': int(main_stream.VideoEncoderConfiguration.RateControl.FrameRateLimit),
                'bitrate': int(main_stream.VideoEncoderConfiguration.RateControl.BitrateLimit),
                'quality': 4.0
            },
            'lowQuality': {
                'rtsp': extract_path(sub_stream.streamUri),
                'snapshot': extract_path(sub_stream.snapshotUri),
                'width': sub_stream.VideoEncoderConfiguration.Resolution.Width,
                'height': sub_stream.VideoEncoderConfiguration.Resolution.Height,
                'framerate': int(sub_stream.VideoEncoderConfiguration.RateControl.FrameRateLimit),
                'bitrate': int(sub_stream.VideoEncoderConfiguration.RateControl.BitrateLimit),
                'quality': 1.0
            },
            'target': {
                'hostname': host_clean,
                'ports': {
                    'rtsp': 554,
                    'snapshot': port
                }
            }
        }
        
        config['onvif'].append(camera_config)
        server_port += 1

    return config