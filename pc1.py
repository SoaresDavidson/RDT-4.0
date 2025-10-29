from JanelaJoao import Envio

IP = '127.0.0.1'
PORTA = 55555

remetente = Envio(IP,PORTA)

try:
    message = input("Digite sua mensagem:  ")

    remetente.enfileirar_mensagens([message])
    remetente.esperar_confirmacao_total()
except KeyboardInterrupt:
    print("Envio interompido")
finally:
    remetente.fechar()

