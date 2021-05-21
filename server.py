import copy
import sys
import getopt
import socket
import random
import queue
import threading
import time
import util


class Server:

    def __init__(self, dest, port, window):
        self.server_addr = dest
        self.server_port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.settimeout(None)
        self.sock.bind((self.server_addr, self.server_port))
        self.window = window
        self.yes = False
        self.all_users = []
        self.address_of_users = {}
        self.incoming_msgs = {}
        self.client_list = {}
        self.end = {}
        self.all_users_str = ''
        self.all_users_and_len = ""

    def start(self):

        while True:
            recieved_packet, adress = self.sock.recvfrom(4096)
            recieved_packet = recieved_packet.decode("utf-8")
            # if checksums don't match drop the message
            if not util.validate_checksum(recieved_packet):
                continue
            # gives the start_resender signal that the start msg has been recieved
            if adress in self.client_list.keys():
                if self.client_list[adress][1] is True:
                    self.client_list[adress][1] = False
            username = ""
            # handles threading of different clients
            # and makes new threads for new clients
            if adress in self.address_of_users.keys():
                username = self.address_of_users[adress]
            if adress in self.incoming_msgs.keys():
                self.incoming_msgs[adress].put(recieved_packet)
            else:
                self.incoming_msgs[adress] = queue.Queue()
                self.incoming_msgs[adress].put(recieved_packet)
                threading.Thread(target=self.handler_server, args=(adress, username)).start()

    # handles sending the window and retransmititng the whole window
    # in case of no new ack
    def sender(self, adress, client_wind, client_queue):
        while True:
            try:
                packet = client_queue.get(timeout=util.TIME_OUT)
                self.sock.sendto(packet.encode("utf=8"), (adress))
            except:
                if client_wind:
                    for number in client_wind.keys():
                        pac = util.make_packet("data", number, client_wind[number])
                        self.sock.sendto(pac.encode("utf-8"),
                                         (adress))
                # if there is nothing in client_wind, that means this
                # particular conversation is finished and hence the thread is stopped
                else:
                    break

    # this is the thread which does eveything for a single client
    def handler_server(self, adress, username):
        '''
        The value corrsponding to each key in the self.client_list dictionary
        is a list and below is what each index in the list stands for:
        [0] = bool to check if a new message is being sent, [1] = bool to check
        if a start message is being sent, [2] = first seq_no created,
        [3] = current seq_no going [4] = dictionary with number chunks equal
        to the window size and their sequence_number, [5]=list wil all chunks,
        [6] = queue for sending chunks in the dictionary, [7] = lenght of the
        list with all the chunks, [8] = bool for cheking if end message is being sent
        '''

        # one time initialization of local variables
        self.client_list[adress] = [None]*9
        self.client_list[adress][4] = {}
        self.client_list[adress][5] = []
        self.client_list[adress][6] = queue.Queue()
        # keeping check of end messages
        self.end[adress] = set()
        fisrt_s_no = 0
        recieved_ack = []
        msg_od = {}

        while True:

            # pre-making the chunks into a list
            def into_chunks(whole_message):
                # generating sequence number and clearing any misc. data
                self.client_list[adress][2] = random.randrange(0, 1000)
                self.client_list[adress][4].clear()
                self.client_list[adress][5].clear()
                self.client_list[adress][6].queue.clear()
                self.client_list[adress][3] = self.client_list[adress][2] + 1

                while len(whole_message) > 0:
                    if len(whole_message) > util.CHUNK_SIZE:
                        self.client_list[adress][5].append(whole_message[:util.CHUNK_SIZE])
                        whole_message = whole_message[util.CHUNK_SIZE:]
                    else:
                        self.client_list[adress][5].append(whole_message)
                        break
                self.client_list[adress][7] = len(self.client_list[adress][5])

                # putting first 3 chunks in queue
                for _ in range(self.window):
                    if self.client_list[adress][5]:
                        self.client_list[adress][4][self.client_list[adress]
                                                    [3]] = self.client_list[adress][5][0]
                        pac = util.make_packet("data", self.client_list[adress][3],
                                               self.client_list[adress][5][0])
                        self.client_list[adress][6].put(pac)
                        del self.client_list[adress][5][0]
                        self.client_list[adress][3] += 1
                    else:
                        break

            # function to get the key from a given value in a dictionary
            def get_key(username):
                for address, user in self.address_of_users.items():
                    if user == username:
                        return address
                return "N/A"

            # function to get the list of usernames and, through that, the list
            # of adresses which a file/message is to be sent
            # and prints on the server the non existent clients
            def get_users(type_func, username, split_msg, users_to_send,
                          no_of_users, adress_to_send):
                print(type_func + ':', username)
                for each_user in range(no_of_users):
                    users_to_send.append(str(split_msg[3+each_user]))
                for name in users_to_send:
                    available = get_key(name)
                    if available == "N/A":
                        print(type_func + ":", username, "to non-existent user", name)
                    else:
                        adress_to_send.append(available)

            recieved_packet = self.incoming_msgs[adress].get()
            type_d, s_no, recieved_message, _ = util.parse_packet(recieved_packet)
            # converting s_no into integer
            s_no = int(s_no)

            if type_d == "start":
                fisrt_s_no = s_no+1
                sent_ack = s_no+1
                # last sent ack
                # below variables are cleared everytime a
                # new start message is sent
                msg_od.clear()
                # msg_od contains the messages that have been recieved
                recieved_ack.clear()
                # contains the acks that have been reccieved
                packet = util.make_packet("ack", fisrt_s_no,)
                self.sock.sendto(packet.encode("utf-8"), (adress))

            elif type_d == "data":
                # concatenation
                if s_no not in recieved_ack:
                    msg_od[s_no] = recieved_message
                    recieved_ack.append(s_no)
                    recieved_ack.sort()
                if s_no == sent_ack:
                    sent_ack = recieved_ack[0]+1
                    for idx in range(len(recieved_ack)-1):
                        if recieved_ack[idx] + 1 == recieved_ack[idx+1]:
                            sent_ack = recieved_ack[idx+1]+1
                        else:
                            break
                packet = util.make_packet("ack", sent_ack,)
                self.sock.sendto(packet.encode("utf-8"), (adress))
                continue

            elif type_d == "ack":
                temp_add = adress
                # if new message is being sent, data copied from list into local variables
                if self.client_list[adress][0] is True:
                    client_wind = copy.deepcopy(self.client_list[temp_add][4])
                    client_queue = queue.Queue()
                    for temp_var in self.client_list[temp_add][6].queue:
                        client_queue.put(temp_var)
                    client_chunks = copy.deepcopy(self.client_list[temp_add][5])
                    client_seq_no = self.client_list[temp_add][3]
                no_to_send = s_no - self.client_list[temp_add][2] - 1

                # if ack for end message is sent
                if no_to_send == self.client_list[temp_add][7]:
                    packet = util.make_packet("end", s_no, )
                    self.client_list[8] = True
                    client_wind.clear()
                    # sending and resending of the end message
                    threading.Thread(target=self.end_resender, args=(packet, adress,)).start()

                # if ack of end message is sent
                elif no_to_send > self.client_list[temp_add][7]:
                    # gives end_resender signal that the end msg has been recieved
                    self.client_list[8] = False
                    # to disconnect user incase of unknown command
                    if self.yes:
                        self.all_users.remove(username)
                        del self.address_of_users[adress]
                        del self.incoming_msgs[adress]
                        print("disconnected:", username, "sent unknown command")
                        self.yes = False
                        break
                        # break will break the while loop and hence finish the thread
                    continue

                else:
                    # if new message start a new thread for sending messages
                    if self.client_list[adress][0] is True:
                        self.client_list[adress][0] = False
                        threading.Thread(target=self.sender, args=(
                            adress, client_wind, client_queue,)).start()
                    # handling sliding window
                    count = 0
                    for k in list(client_wind):
                        if k < s_no:
                            del client_wind[k]
                            count += 1

                    for _ in range(count):
                        if client_chunks:
                            client_wind[client_seq_no] = client_chunks[0]
                            pac = util.make_packet("data", client_seq_no, client_chunks[0])
                            client_queue.put(pac)
                            del client_chunks[0]
                            client_seq_no += 1
                        else:
                            continue

            elif type_d == "end":
                # sending and resending ack of end
                if s_no in self.end[adress]:
                    packet_ack = util.make_packet("ack", s_no + 1,)
                    self.sock.sendto(packet_ack.encode("utf-8"), (adress))
                    continue
                self.end[adress].add(s_no)

                # concatenating the whole messgae sent
                complete_msg = ""
                packet_ack = util.make_packet("ack", s_no + 1,)
                self.sock.sendto(packet_ack.encode("utf-8"), (adress))
                for order_no in range(fisrt_s_no, s_no):
                    if order_no in msg_od.keys():
                        complete_msg = complete_msg + msg_od[order_no]

                try:
                    split_msg = complete_msg.split(" ")
                    msg_type = split_msg[0]
                    if msg_type in ("join", "disconnect"):
                        username = " ".join(split_msg[2:])

                    # handling different messages
                    if msg_type == "join":
                        if len(self.all_users) >= util.MAX_NUM_CLIENTS:
                            whole_message = util.make_message("err_server_full", 2)
                            into_chunks(whole_message)
                            self.client_list[adress][0] = True
                            self.client_list[adress][1] = True
                            packet = util.make_packet("start", self.client_list[adress][2],)
                            # sending and resending of start message
                            threading.Thread(target=self.start_resender,
                                             args=(packet, adress,)).start()

                        elif username in self.all_users:
                            whole_message = util.make_message("err_username_unavailable", 2)
                            into_chunks(whole_message)
                            self.client_list[adress][0] = True
                            self.client_list[adress][1] = True
                            packet = util.make_packet("start", self.client_list[adress][2],)
                            threading.Thread(target=self.start_resender,
                                             args=(packet, adress,)).start()

                        else:
                            print("join:", username)
                            self.all_users.append(username)
                            self.address_of_users[adress] = username
                            self.all_users.sort()

                    elif msg_type == "request_users_list":
                        print('request_users_list:', username)
                        self.all_users_str = " ".join(self.all_users)
                        self.all_users_and_len = str(len(self.all_users)) + " " + self.all_users_str
                        whole_message = util.make_message(
                            "response_users_list", 3, self.all_users_and_len)
                        into_chunks(whole_message)
                        self.client_list[adress][0] = True
                        self.client_list[adress][1] = True
                        packet = util.make_packet("start", self.client_list[adress][2],)
                        threading.Thread(target=self.start_resender, args=(packet, adress,)).start()

                    elif msg_type == "disconnect":
                        print("disconnected:", username)
                        self.all_users.remove(username)
                        del self.address_of_users[adress]
                        del self.incoming_msgs[adress]
                        break

                    elif msg_type == "send_message":
                        no_of_users = int(split_msg[2])
                        users_to_send = []
                        adress_to_send = []
                        get_users("msg", username, split_msg, users_to_send,
                                  no_of_users, adress_to_send)
                        to_send = "1 " + username + " " + (" ".join(split_msg[no_of_users+3:]))
                        if " ".join(split_msg[no_of_users+3]) == " ":
                            int("w")
                        whole_message = util.make_message(
                            "forward_message", 4, to_send)
                        into_chunks(whole_message)
                        packet = util.make_packet("start", self.client_list[adress][2],)
                        for add in adress_to_send:
                            self.client_list[add] = copy.copy(self.client_list[adress])
                            self.client_list[add][0] = True
                            self.client_list[add][1] = True
                            threading.Thread(target=self.start_resender,
                                             args=(packet, add,)).start()

                    elif msg_type == "send_file":
                        no_of_users = int(split_msg[2])
                        users_to_send = []
                        adress_to_send = []
                        get_users("file", username, split_msg,
                                  users_to_send, no_of_users, adress_to_send)
                        to_send = "1 " + username + " " + (" ".join(split_msg[no_of_users+3:]))
                        whole_message = util.make_message(
                            "forward_file", 4, to_send)
                        into_chunks(whole_message)
                        packet = util.make_packet("start", self.client_list[adress][2],)
                        for add in adress_to_send:
                            self.client_list[add] = copy.copy(self.client_list[adress])
                            self.client_list[add][0] = True
                            self.client_list[add][1] = True
                            threading.Thread(target=self.start_resender,
                                             args=(packet, add,)).start()
                    else:
                        # to give traceback error and start the except loop
                        int("w")

                # to cater for messages that have correct userinput format
                # but still send the wrong message
                except:
                    whole_message = util.make_message("err_unknown_message", 2)
                    into_chunks(whole_message)
                    self.client_list[adress][0] = True
                    self.client_list[adress][1] = True
                    packet = util.make_packet("start", self.client_list[adress][2],)
                    threading.Thread(target=self.start_resender, args=(packet, adress,)).start()
                    self.yes = True

    # function to handle the sending and restransmissions of "start"
    def start_resender(self, packet, adress):
        while self.client_list[adress][1] is True:
            self.sock.sendto(packet.encode("utf-8"), (adress))
            time.sleep(util.TIME_OUT)

    # function to handle the sending and restransmissions of "end"
    def end_resender(self, packet, adress):
        while self.client_list[8] is True:
            self.sock.sendto(packet.encode("utf-8"), (adress))
            time.sleep(util.TIME_OUT)


if __name__ == "__main__":
    def helper():

        print("Server")
        print("-p PORT | --port=PORT The server port, defaults to 15000")
        print("-a ADDRESS | --address=ADDRESS The server ip or hostname, defaults to localhost")
        print("-w WINDOW | --window=WINDOW The window size, default is 3")
        print("-h | --help Print this help")

    try:
        OPTS, ARGS = getopt.getopt(sys.argv[1:],
                                   "p:a:w", ["port=", "address=", "window="])
    except getopt.GetoptError:
        helper()
        exit()

    PORT = 15000
    DEST = "localhost"
    WINDOW = 3

    for o, a in OPTS:
        if o in ("-p", "--port="):
            PORT = int(a)
        elif o in ("-a", "--address="):
            DEST = a
        elif o in ("-w", "--window="):
            WINDOW = a

    SERVER = Server(DEST, PORT, WINDOW)
    try:
        SERVER.start()
    except (KeyboardInterrupt, SystemExit):
        exit()
