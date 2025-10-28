from functs import seg_message, decode_segments
import Janela
message = input("digite sua mensagem: ")


segments = seg_message(message)

print(segments[0])
print(decode_segments(segments))