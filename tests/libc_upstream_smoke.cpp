// Android ABI contracts for the newly imported upstream symbols.
#include <libc_shim.h>
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <cstring>
#include <cstdlib>
#include <climits>
#include <cerrno>
#include <cstdio>
#include <unordered_map>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <sys/uio.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <poll.h>
#include <unistd.h>
#include <chrono>
#include <cstdint>

struct AndroidMessage {
    void* name; unsigned int name_size;
    iovec* vectors; size_t vector_count;
    void* control; size_t control_size; int flags;
};
struct AndroidBatch { AndroidMessage header; unsigned int length; };

int main() {
    std::unordered_map<std::string, void*> symbols;
    for(auto& s : shim::get_shimmed_symbols()) symbols[s.name] = s.value;
    char** environment = *static_cast<char***>(symbols.at("environ"));
    assert(environment && environment[0] && std::strchr(environment[0], '='));
    auto gnuError = reinterpret_cast<char*(*)(int,char*,size_t)>(symbols.at("__gnu_strerror_r"));
    char errorText[256]{};
    char* message = gnuError(2,errorText,sizeof(errorText));
    assert(message && std::strlen(message)>0 && std::strcmp(message, ::strerror(ENOENT))==0);
    auto getError = reinterpret_cast<int*(*)()>(symbols.at("__errno"));
    auto checkedRead = reinterpret_cast<size_t(*)(void*,size_t,size_t,void*,size_t)>(symbols.at("__fread_chk"));
    auto checkedWrite = reinterpret_cast<size_t(*)(const void*,size_t,size_t,void*,size_t)>(symbols.at("__fwrite_chk"));
    auto checkedPoll = reinterpret_cast<int(*)(pollfd*,unsigned int,int,size_t)>(symbols.at("__poll_chk"));
    // Guard failures must occur before touching a null stream or undersized array.
    for(int test=0;test<3;test++) {
        pid_t child=fork();assert(child>=0);
        if(child==0) {
            rlimit limit{0,0};setrlimit(RLIMIT_CORE,&limit);
            if(test==0) checkedRead(errorText,SIZE_MAX,2,nullptr,sizeof(errorText));
            if(test==1) checkedWrite(errorText,SIZE_MAX,2,nullptr,sizeof(errorText));
            if(test==2) checkedPoll(nullptr,2,0,0);
            _exit(1);
        }
        int status=0;assert(waitpid(child,&status,0)==child);
        assert(WIFSIGNALED(status) && WTERMSIG(status)==SIGABRT);
    }
    auto sendFile = reinterpret_cast<ssize_t(*)(int,int,int64_t*,size_t)>(symbols.at("sendfile"));
    FILE* file=tmpfile();assert(file);assert(fwrite("abcdef",1,6,file)==6);fflush(file);
    // Darwin sendfile needs a TCP socket.
    int listener=socket(AF_INET,SOCK_STREAM,0);assert(listener>=0);
    sockaddr_in endpoint{};endpoint.sin_family=AF_INET;endpoint.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    assert(bind(listener,reinterpret_cast<sockaddr*>(&endpoint),sizeof(endpoint))==0);
    socklen_t endpointSize=sizeof(endpoint);assert(getsockname(listener,reinterpret_cast<sockaddr*>(&endpoint),&endpointSize)==0);
    assert(listen(listener,1)==0);
    int writer=socket(AF_INET,SOCK_STREAM,0);assert(connect(writer,reinterpret_cast<sockaddr*>(&endpoint),endpointSize)==0);
    int reader=accept(listener,nullptr,nullptr);assert(reader>=0);
    assert(lseek(fileno(file),0,SEEK_SET)==0);
    int64_t position=1;
    assert(sendFile(-1,fileno(file),&position,3)==-1 && position==1);
    assert(sendFile(writer,-1,&position,3)==-1 && position==1);
    assert(sendFile(writer,fileno(file),&position,0)==0 && position==1);
    assert(sendFile(writer,fileno(file),&position,3)==3 && position==4);
    assert(lseek(fileno(file),0,SEEK_CUR)==0);
    char bytes[8]{};assert(read(reader,bytes,3)==3 && !memcmp(bytes,"bcd",3));
    assert(sendFile(writer,fileno(file),nullptr,2)==2);
    assert(lseek(fileno(file),0,SEEK_CUR)==2);
    assert(read(reader,bytes,2)==2 && !memcmp(bytes,"ab",2));
    close(reader);close(writer);close(listener);fclose(file);
    auto sendBatch=reinterpret_cast<int(*)(int,AndroidBatch*,unsigned int,int)>(symbols.at("sendmmsg"));
    auto recvBatch=reinterpret_cast<int(*)(int,AndroidBatch*,unsigned int,int,const timespec*)>(symbols.at("recvmmsg"));
    int pair[2];assert(socketpair(AF_UNIX,SOCK_DGRAM,0,pair)==0);
    char first[]="one",second[]="two";iovec payloads[]={{first,3},{second,3}};
    AndroidBatch outgoing[2]{};
    for(int i=0;i<2;i++) { outgoing[i].header.vectors=&payloads[i];outgoing[i].header.vector_count=1; }
    assert(sendBatch(pair[0],outgoing,2,0)==2);
    assert(outgoing[0].length==3 && outgoing[1].length==3);
    char received[2][8]{};iovec buffers[]={{received[0],8},{received[1],8}};
    struct { AndroidBatch messages[2]; uint64_t guard; } target{};target.guard=0xa1b2c3d4;
    for(int i=0;i<2;i++) { target.messages[i].header.vectors=&buffers[i];target.messages[i].header.vector_count=1; }
    timespec timeout{0,50000000};
    assert(recvBatch(pair[1],target.messages,2,0,&timeout)==2);
    assert(target.messages[0].length==3 && target.messages[1].length==3 && target.guard==0xa1b2c3d4);
    assert(!memcmp(received[0],"one",3) && !memcmp(received[1],"two",3));
    auto start=std::chrono::steady_clock::now();
    assert(recvBatch(pair[1],target.messages,1,0,&timeout)==0);
    assert(std::chrono::steady_clock::now()-start<std::chrono::seconds(1));
    assert(recvBatch(pair[1],target.messages,1,0x40,nullptr)==-1 && *getError()==11);
    // WAITFORONE must not block waiting for another datagram after the first.
    assert(sendBatch(pair[0],outgoing,1,0)==1);
    assert(recvBatch(pair[1],target.messages,2,0x10000,nullptr)==1);
    assert(target.guard==0xa1b2c3d4);
    // A small receive buffer reports Android MSG_TRUNC without overwriting it.
    buffers[0].iov_len=1;
    assert(sendBatch(pair[0],outgoing,1,0)==1);
    assert(recvBatch(pair[1],target.messages,1,0x40,nullptr)==1);
    assert(target.messages[0].length==1 && (target.messages[0].header.flags & 0x20));
    assert(recvBatch(pair[1],target.messages,1,0x4000,nullptr)==-1 && *getError()==22);
    outgoing[0].header.control=bytes;outgoing[0].header.control_size=sizeof(bytes);
    assert(sendBatch(pair[0],outgoing,1,0)==-1 && *getError()!=0);
    close(pair[0]);close(pair[1]);
    // Verify destination/source sockaddr translation, not only connected sockets.
    int udp=socket(AF_INET,SOCK_DGRAM,0);assert(udp>=0);
    endpoint.sin_port=0;
    assert(bind(udp,reinterpret_cast<sockaddr*>(&endpoint),sizeof(endpoint))==0);
    endpointSize=sizeof(endpoint);assert(getsockname(udp,reinterpret_cast<sockaddr*>(&endpoint),&endpointSize)==0);
    struct AndroidAddress { uint16_t family,port; uint32_t address; char padding[8]; } destination{};
    destination.family=2;destination.port=endpoint.sin_port;destination.address=endpoint.sin_addr.s_addr;
    outgoing[0].header.control=nullptr;outgoing[0].header.control_size=0;
    outgoing[0].header.name=&destination;outgoing[0].header.name_size=sizeof(destination);
    assert(sendBatch(udp,outgoing,1,0)==1);
    AndroidAddress from{};target.messages[0].header.name=&from;
    target.messages[0].header.name_size=sizeof(from);buffers[0].iov_len=8;
    assert(recvBatch(udp,target.messages,1,0,&timeout)==1);
    assert(from.family==2 && from.port==endpoint.sin_port && from.address==endpoint.sin_addr.s_addr);
    assert(target.messages[0].header.name==&from && target.messages[0].header.name_size==sizeof(from));
    close(udp);
    puts("PASS: environ, GNU strerror, fortify, sendfile, Android batch-message ABI and timeouts");
}
