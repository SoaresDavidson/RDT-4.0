import random
import socket, threading, time
from enum import Enum

HOST = '127.0.0.1'  
PORT = 55555        
BUFFER_SIZE = 4096
TIMEOUT_TIMER = 300.0 # Timeout do servidor, não do RDT
MSS = 2

# class syntax
class Operations(Enum):
    NORMAL = 1
    PERDA = 2
    CORRUPÇÃO = 3
    ATRASO = 4
    DUPLICAÇÃO = 5
    REORDENAÇÃO = 6

op_atual = Operations.NORMAL
        

class Servidor:
    def __init__(self, HOST, PORT, BUFFER_SIZE, TIMEOUT_TIMER, MSS):
        self.host = HOST
        self.port = PORT
        self.buffer_size = BUFFER_SIZE
        self.timeout_timer = TIMEOUT_TIMER
        self.mss = MSS
        self.pc1_addr = None
        self.pc2_addr = None
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_socket.bind((HOST, PORT))
        self.server_socket.settimeout(TIMEOUT_TIMER)
        print(f"Servidor (Roteador B) iniciado em {HOST}:{PORT}")
        print(f"Operação atual: {op_atual.name}")

    def start_server(self):
        try:
            while True:
                bytes_recebidos, remetente = self.server_socket.recvfrom(BUFFER_SIZE)
                
                # Aprende os endereços dos PCs
                if self.pc1_addr is None:
                    self.pc1_addr = remetente
                    print(f"[Roteador] PC1 (Remetente) registrado: {remetente}")
                    continue # Ignora o primeiro pacote (é só para registro)
                elif self.pc2_addr is None and self.pc1_addr != remetente:
                    self.pc2_addr = remetente
                    print(f"[Roteador] PC2 (Destinatário) registrado: {remetente}")
                    continue # Ignora o primeiro pacote (é só para registro)
                
                # Uma vez que ambos estão registrados, começa a encaminhar
                if self.pc1_addr and self.pc2_addr:
                    self.receber_mensagem(bytes_recebidos, remetente)

        except socket.timeout:
            print(f"[Roteador] Servidor inativo a muito tempo, encerrando...")
        except OSError as e:
            print(f"[Roteador] Erro no servidor: {e}")
        finally:
            self.server_socket.close()
            print("[Roteador] Servidor encerrado.")


    def receber_mensagem(self, bytes_recebidos, addr):
        # !!! BUG FIX: 'segmento' deve ser definido a partir dos bytes recebidos
        segmento = bytes_recebidos
        
        try:
            if not bytes_recebidos:
                print(f"[Roteador] Pacote vazio recebido de {addr}.")
                return

            match (op_atual):
                case Operations.NORMAL:
                    # Envio normal
                    self.enviar_mensagem(addr, segmento)
                case Operations.PERDA:
                    # Não envia a mensagem
                    print(f"--- [Roteador] PACOTE PERDIDO de {addr} ---")
                    pass  
                case Operations.CORRUPÇÃO:
                    # Corrompe um byte aleatório no payload
                    segmento_corrompido = bytearray(segmento)
                    if len(segmento_corrompido) > 5: # Garante que há dados para corromper
                        # Corrompe um byte (ex: depois de 'SEQ:N:' ou 'ACK:N')
                        idx_corromper = random.randint(0, len(segmento_corrompido) - 1)
                        byte_original = segmento_corrompido[idx_corromper]
                        segmento_corrompido[idx_corromper] = random.randint(0, 255)
                        print(f"--- [Roteador] PACOTE CORROMPIDO de {addr} (Byte {idx_corromper} de {byte_original} para {segmento_corrompido[idx_corromper]}) ---")
                    self.enviar_mensagem(addr, segmento_corrompido)
                case Operations.ATRASO:
                    # Atraso de 1 segundo
                    print(f"--- [Roteador] PACOTE ATRASADO de {addr} ---")
                    time.sleep(1)
                    self.enviar_mensagem(addr, segmento)
                case Operations.DUPLICAÇÃO:
                    # Envia o pacote duas vezes
                    print(f"--- [Roteador] PACOTE DUPLICADO de {addr} ---")
                    self.enviar_mensagem(addr, segmento)
                    time.sleep(0.1) # Pequeno delay para o duplicado
                    self.enviar_mensagem(addr, segmento)
                case Operations.REORDENAÇÃO:
                    # TODO: Implementar lógica de reordenação (requer buffer)
                    print(f"[Roteador] REORDENAÇÃO não implementado. Enviando normalmente.")
                    self.enviar_mensagem(addr, segmento)

        except Exception as e:
            print(f"[Roteador] Erro em receber_mensagem: {e}")


    def mudar_operacao(self):
        global op_atual
        while True:
            try:
                print("\nOpções: NORMAL, PERDA, CORRUPÇÃO, ATRASO, DUPLICAÇÃO")
                nova_op = input("Digite a nova operação do roteador: ").strip().upper()
                match nova_op:
                    case "NORMAL":
                        op_atual = Operations.NORMAL
                    case "PERDA":
                        op_atual = Operations.PERDA
                    case "CORRUPÇÃO":
                        op_atual = Operations.CORRUPÇÃO
                    case "ATRASO":
                        op_atual = Operations.ATRASO
                    case "DUPLICAÇÃO":
                        op_atual = Operations.DUPLICAÇÃO
                    case "REORDENAÇÃO":
                        op_atual = Operations.REORDENAÇÃO
                print(f"==> Operação atual alterada para: {op_atual.name} <==")
            except KeyboardInterrupt:
                print("\nEncerrando mudança de operação.")
                break
            except EOFError:
                break
                

    def enviar_mensagem(self, addr, mensagem):
        try:
            dest = None
            if addr == self.pc1_addr:
                dest = self.pc2_addr
            elif addr == self.pc2_addr:
                dest = self.pc1_addr
            
            if dest:
                self.server_socket.sendto(mensagem, dest)
                # Usar repr() para imprimir bytes de forma segura (UTF-8 pode falhar se corrompido)
                print(f"[Roteador] Mensagem de {addr} encaminhada para {dest}: {repr(mensagem[12:60])}...")
            # else:
            #    print(f"[Roteador] Destinatário desconhecido para {addr}. Pacote descartado.")
        except Exception as e:
                print(f"[Roteador] Erro ao enviar mensagem: {e}")



if __name__ == "__main__":
    servidor = Servidor(HOST, PORT, BUFFER_SIZE, TIMEOUT_TIMER, MSS)
    server_thread = threading.Thread(target=servidor.start_server, daemon=True)
    server_thread.start()
    
    # Permite que o usuário mude a operação
    servidor.mudar_operacao()
    print("Encerrando programa principal...")