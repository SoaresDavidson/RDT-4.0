from functs import seg_message, decode_segments
import Janela
# message = input("digite sua mensagem: ")


# segments = seg_message(message)
envio = Janela.EnviadorSR('127.0.0.1', 55555)
try:
    while True:
        mensagem = input("Digite sua mensagem: ")
        envio.enviar_e_esperar(mensagem)
        input("enviar?")
finally:
    envio.fechar()

# print(segments[0])
# print(decode_segments(segments))