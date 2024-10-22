import sys
import os
import time
import numpy
import threading
import base64
from collections import deque

import webrtcvad

from base import RemdisModule, RemdisUpdateType

class Audio_VAD_VAP(RemdisModule):
    def __init__(self, 
                 pub_exchanges=['vap'],
                 sub_exchanges=['ain']):
        super().__init__(pub_exchanges=pub_exchanges,
                         sub_exchanges=sub_exchanges)

        # VAD parameters
        self.sample_rate = 16000  # Must be 8000, 16000, 32000, or 48000
        self.frame_duration_ms = 30  # Frame duration in ms: 10, 20, or 30 ms
        self.frame_size = int(self.sample_rate * self.frame_duration_ms / 1000)  # Number of samples per frame
        self.frame_bytes = self.frame_size * 2  # Each sample is 2 bytes (int16)

        # VAD object
        self.vad = webrtcvad.Vad(3)  # Aggressiveness: 0-3

        # Silence detection parameters
        self.silence_threshold = 0.5  # Set to 0.5 seconds for 500ms threshold

        # State variables
        self.speech_state = 'silence'  # 'speech' or 'silence'
        self.speech_end_time = None

        # Buffer to hold audio data
        self.audio_buffer = b''

        # Lock for threading
        self.lock = threading.Lock()

    def run(self):
        # Start thread to receive audio data
        t1 = threading.Thread(target=self.receive_audio_loop)
        # Start thread to process audio data
        t2 = threading.Thread(target=self.process_audio_loop)

        t1.start()
        t2.start()

        t1.join()
        t2.join()

    def receive_audio_loop(self):
        self.subscribe('ain', self.audio_callback)

    def audio_callback(self, ch, method, properties, in_msg):
        in_msg = self.parse_msg(in_msg)
        # The audio data is in in_msg['body'], base64 encoded
        chunk = base64.b64decode(in_msg['body'].encode())
        # Append to buffer
        with self.lock:
            self.audio_buffer += chunk

    def process_audio_loop(self):
        while True:
            with self.lock:
                if len(self.audio_buffer) >= self.frame_bytes:
                    frame = self.audio_buffer[:self.frame_bytes]
                    self.audio_buffer = self.audio_buffer[self.frame_bytes:]
                else:
                    frame = None

            if frame:
                # Ensure the frame is in bytes and has the correct length
                if len(frame) != self.frame_bytes:
                    continue  # Skip frames that are not the correct size

                is_speech = self.vad.is_speech(frame, self.sample_rate)

                current_time = time.time()

                if is_speech: 
                    if self.speech_state == 'silence':
                        # Speech has started
                        print("Speech has started...")
                        self.speech_state = 'speech'
                    self.speech_end_time = None  # Reset speech end time
                else:
                    if self.speech_state == 'speech':
                        if self.speech_end_time is None:
                            self.speech_end_time = current_time
                        else:
                            if (current_time - self.speech_end_time) >= self.silence_threshold:
                                # Silence has lasted long enough, consider speech ended
                                print("Silence threshold reached (500ms), speech has ended...")
                                self.speech_state = 'silence'
                                self.speech_end_time = None
                                # Send message to 'vap' exchange
                                snd_iu = self.createIU('SYSTEM_TAKE_TURN', 'str', RemdisUpdateType.ADD)
                                self.publish(snd_iu, 'vap')
                    else:
                        # Already in silence state
                        self.speech_end_time = None
            else:
                # Sleep briefly to avoid busy waiting
                time.sleep(0.01)



def main():
    vad_vap = Audio_VAD_VAP()
    vad_vap.run()

if __name__ == '__main__':
    main()