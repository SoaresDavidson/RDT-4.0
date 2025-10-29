import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

public class MaquinaC {
    private static final String HOST = "127.0.0.1";
    private static final int PORT = 55555;
    private static final int BUFFER_SIZE = 4096;
    private static final int WINDOW_SIZE = 5;
    private static final int SEQ_MODULO = 10;

    private static int rcv_base = 0; 
    private static Map<Integer, String> ooo_buffer = new HashMap<>(); // Buffer para pacotes fora de ordem 

    // Camada de aplicação
    private static void deliverData(String data) {
        System.out.println("-> [CAMADA SUPERIOR] Dados entregues: " + data);
    }

    // Cria um pacote ACK no formato esperado por Janela.py
    private static byte[] makeAckPacket(int ackNum) {
        int seq = -1; // -1 para indicar que não é um pacote de dados
        int flag_ack = 1; // Flag 1 para indicar que é um ACK

    // Monta o cabeçalho de 12 bytes
        byte[] header = new byte[12];

        // Seq
        header[0] = (byte)(seq >> 24);
        header[1] = (byte)(seq >> 16);
        header[2] = (byte)(seq >> 8);
        header[3] = (byte)(seq);

        // Ack
        header[4] = (byte)(ackNum >> 24);
        header[5] = (byte)(ackNum >> 16);
        header[6] = (byte)(ackNum >> 8);
        header[7] = (byte)(ackNum);

        // Flag
        int bits_flag = (flag_ack & 1) << 31;
        header[8] = (byte)(bits_flag >> 24);
        header[9] = (byte)(bits_flag >> 16);
        header[10] = (byte)(bits_flag >> 8);
        header[11] = (byte)(bits_flag);

        return header;
    }

    // Envia um pacote ACK para o roteador
    private static void sendAck(DatagramSocket socket, InetAddress routerAddr, int routerPort, int ackNum) throws IOException {
        byte[] ackData = makeAckPacket(ackNum);
        DatagramPacket ackPacket = new DatagramPacket(ackData, ackData.length, routerAddr, routerPort);
        socket.send(ackPacket);
        System.out.println("[Maquina C] Enviando ACK para o pacote: " + ackNum);
    }

    // Verifica se um número de sequência está na janela de recepção
    private static boolean isInWindow(int seqNum) {
        int end = (rcv_base + WINDOW_SIZE) % SEQ_MODULO;
        if (rcv_base < end) { // Janela não dá a volta
            return seqNum >= rcv_base && seqNum < end;
        } else { // Janela dá a volta (ex: base=8, fim=3, janela={8,9,0,1,2})
            return seqNum >= rcv_base || seqNum < end;
        }
    }

    /**
    * Calcula a soma de complemento de um de 16 bits
    * @param a Palavra A de 16 bits
    * @param b Palavra B de 16 bits
    * @return A soma de complemento de um (16 bits)
    */
   private static int binarySum(int a, int b) {
    int soma = a + b;
    soma = (soma & 0xFFFF) + (soma >> 16);
    return soma & 0xFFFF;
}

    /**
     * Calcula o checksum para um array de bytes
     * @param data O array de bytes do pacote
     * @param length O comprimento real dos dados no array
     * @return O checksum (soma de complemento de um) de 16 bits
     */
    private static int calculateChecksum(byte[] data, int length) {
        int result = 0;
        int i = 0;

        while (i < length) {
            // Combina dois bytes em uma palavra de 16 bits (Word)
            // (data[i] & 0xFF) << 8 : Byte mais significativo (MSB)
            int word = ((data[i] & 0xFF) << 8);

            if (i + 1 < length) {
                // (data[i+1] & 0xFF) : Byte menos significativo (LSB)
                word |= (data[i+1] & 0xFF);
            } else {
                // Comprimento ímpar. O ljust('0') do Python significa
                // que o byte LSB é 0x00, o que já é o caso em 'word'.
            }

            // Acumula a soma
            result = binarySum(result, word);

            i += 2; // Move para a próxima palavra de 16 bits
        }
        System.out.println(result);
        return result;
    }

    public static void main(String[] args) {
        System.out.println("[Maquina C] Destinatario RDT (Selective Repeat) iniciado.");

        try (DatagramSocket socket = new DatagramSocket()) {

             InetAddress routerAddress = InetAddress.getByName(HOST);

            // Envia um pacote inicial para o roteador aprender seu endereço
            byte[] initData = "INIT_PC2".getBytes(StandardCharsets.UTF_8);
            DatagramPacket initPacket = new DatagramPacket(initData, initData.length, routerAddress, PORT);
            socket.send(initPacket);
            System.out.println("[Maquina C] Pacote de inicializacao enviado para o Roteador B.");

            byte[] buffer = new byte[BUFFER_SIZE];

            while (true) {
                DatagramPacket receivePacket = new DatagramPacket(buffer, buffer.length);
                socket.receive(receivePacket);

                byte[] receivedData = receivePacket.getData();
                int length = receivePacket.getLength();

                if (length < 12) {
                    System.out.println("[Maquina C] Recebeu pacote muito curto (ignorando): " + new String(receivedData, 0, length));
                    continue;
                }

                // O checksum está nos bytes 8 e 9 (primeiros 16 bits da 3ª linha do header)

                // Extrai o checksum recebido
                int checksum_rcv = ((receivedData[8] & 0xFF) << 8) | (receivedData[9] & 0xFF);

                // Cria uma cópia do pacote com o campo checksum zerado
                byte[] zeroedData = new byte[length];
                System.arraycopy(receivedData, 0, zeroedData, 0, length);
                zeroedData[8] = 0; // Zera o byte 8 (Checksum MSB)
                zeroedData[9] = 0; // Zera o byte 9 (Checksum LSB)

                // Calcula o checksum sobre o pacote zerado
                int checksum_calc = calculateChecksum(zeroedData, length);

                // Compara
                if (checksum_rcv != checksum_calc) {
                    System.out.println("\n[Maquina C] PACOTE CORROMPIDO! Checksum falhou.");
                    System.out.println("  -> Esperado: " + checksum_rcv + ", Calculado: " + checksum_calc);
                    // No selective repeat, pacotes corrompidos são silenciosamente descartados.
                    // O remetente sofrerá timeout para este pacote e reenviará
                    continue; // Descarta o pacote
                } 


                // Lendo o cabeçalho manualmente (bytes_para_int)
                long seqNum_long = 0;
                for(int i=0; i<4; i++) seqNum_long = (seqNum_long << 8) | (receivedData[i] & 0xFF);
                int seqNum = (int) seqNum_long;

                String data = new String(receivedData, 12, length - 12, StandardCharsets.UTF_8);

                System.out.println("\n[Maquina C] Recebeu pacote. Seq: " + seqNum + ", Dados: '" + data + "' (Checksum OK)");

                // Receptor seletivo
                if (isInWindow(seqNum)) {
                    // Pacote está dentro da janela, envia ACK para ele
                    sendAck(socket, routerAddress, PORT, seqNum);

                    if (seqNum == rcv_base) {
                        // Pacote esperado, entrega para a camada superior
                        deliverData(data);

                        // Avança a base da janela e entrega pacotes do buffer que se tornaram contíguos
                        rcv_base = (rcv_base + 1) % SEQ_MODULO;
                        while (ooo_buffer.containsKey(rcv_base)) {
                            String bufferedData = ooo_buffer.remove(rcv_base);
                            deliverData(bufferedData);
                            System.out.println("[Maquina C] Entregou pacote " + rcv_base + " do buffer.");
                            rcv_base = (rcv_base + 1) % SEQ_MODULO;
                        }
                        System.out.println("[Maquina C] Janela avançou. Nova base: " + rcv_base);

                    } else {
                        // Pacote fora de ordem, mas na janela
                        if (!ooo_buffer.containsKey(seqNum)) {
                            ooo_buffer.put(seqNum, data);
                            System.out.println("[Maquina C] Pacote " + seqNum + " fora de ordem, armazenado no buffer.");
                        }
                    }
                } else {
                    // Verifica se é um pacote antigo que já foi confirmado na janela anterior
                    int prev_window_base = (rcv_base - WINDOW_SIZE + SEQ_MODULO) % SEQ_MODULO;
                    boolean is_old_ack;
                    if (prev_window_base < rcv_base) {
                        is_old_ack = seqNum >= prev_window_base && seqNum < rcv_base;
                    } else {
                        is_old_ack = seqNum >= prev_window_base || seqNum < rcv_base;
                    }

                    if(is_old_ack) {
                        // Pacote já foi recebido e entregue mas ACK pode ter se perdido.
                        System.out.println("[Maquina C] Recebeu pacote antigo (Seq: " + seqNum + "). Reenviando ACK.");
                        sendAck(socket, routerAddress, PORT, seqNum);
                    } else {
                        System.out.println("[Maquina C] Pacote fora da janela (descartado). (Base: " + rcv_base + ", Recebido: " + seqNum + ")");
                    }
                }
            }

        } catch (IOException e) {
            System.err.println("[Maquina C] Erro de I/O: " + e.getMessage());
            e.printStackTrace();
        }

        System.out.println("[Maquina C] Destinatario finalizado.");
    }
}
