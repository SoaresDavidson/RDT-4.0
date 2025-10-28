import sys, time
# Importa a classe do enviador e as constantes do arquivo Janela.py
from Janela import EnviadorSR, IP_ROTEADOR, PORTA_ROTEADOR

# --- Programa Principal (Remetente com Selective Repeat) ---
if __name__ == '__main__':
    # Cria uma instância do enviador SR, que gerencia toda a lógica de sockets,
    # threads, timers e janelas.
    enviador = EnviadorSR(IP_ROTEADOR, PORTA_ROTEADOR)
    
    print("[PC1] Remetente RDT (Selective Repeat) iniciado.")
    print("Digite as mensagens a serem enviadas. Digite 'exit' para sair ou 'send' para enviar um lote.")

    mensagens_para_enviar = []

    try:
        while True:
            # Coleta múltiplas mensagens do usuário antes de enviar
            mensagem = input(">> ")
            
            if mensagem.lower() == 'exit':
                break
            
            if mensagem.lower() == 'send':
                if not mensagens_para_enviar:
                    print("Nenhuma mensagem para enviar.")
                    continue
                
                print(f"\n--- Enviando lote de {len(mensagens_para_enviar)} mensagens ---")
                # O método enviar_e_esperar é bloqueante: ele só retorna
                # depois que todos os pacotes do lote forem confirmados (ACK).
                enviador.enviar_e_esperar(mensagens_para_enviar)
                print("--- Lote enviado e confirmado com sucesso! ---\n")
                mensagens_para_enviar = [] # Limpa o lote
            else:
                # Adiciona a mensagem à lista para o próximo envio
                mensagens_para_enviar.append(mensagem)
                print(f"Mensagem '{mensagem}' adicionada ao lote. Digite 'send' para enviar.")

    except KeyboardInterrupt:
        print("\nEncerrando remetente...")
    except Exception as e:
        print(f"Ocorreu um erro inesperado: {e}")
    finally:
        # Garante que o enviador e seus recursos (threads, socket) sejam encerrados
        print("Finalizando o enviador...")
        enviador.fechar()
        print("Remetente encerrado.")