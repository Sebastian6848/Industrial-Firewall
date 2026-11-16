#include <iostream>
#include <pugixml/pugixml.hpp>
#include <cstdlib>
#include <string>
#include <cstring>
#include <cctype>
#include <thread>
#include <chrono>
#include <mqtt/async_client.h>
#include <httplib/httplib.h>
#ifdef _WIN32
#include <Windows.h>
#endif // _WIN32

#include "main.h"
#include "Config.h"
#include <OPCUAServer.h>
#include "OPCUAAdapter.h"
//#include <Utils.h>
//#include <iostream>
//#include <windows.h>
//#include <map>
//#include <cmath>
//tools::PathParse pathparse;
int main(int argc, char* argv[])
{

//#ifdef _WIN32
//	SetConsoleOutputCP(65001);
//	CreateThread(NULL,0, (LPTHREAD_START_ROUTINE)thread_opcuaServer,NULL,0,NULL);
//#elif __linux__
//	pthread_t tid;
//	int err = pthread_create(&tid, NULL, thr_fn, &cont);
//#endif // _WIN32
	//nlohmann::json config;
	//try {
	//	std::ifstream file("../../../conf/testmodel.json");
	//	config = nlohmann::json::parse(file);
	//}
	//catch (nlohmann::json::parse_error& e) {
	//	// output exception information
	//	std::cout << "message: " << e.what() << '\n'
	//		<< "exception id: " << e.id << '\n'
	//		<< "byte position of error: " << e.byte << std::endl;
	//}
	//catch (nlohmann::json::type_error& e)
	//{
	//	// output exception information
	//	std::cout << "message: " << e.what() << '\n'
	//		<< "exception id: " << e.id << std::endl;
	//}

	//std::string s= config["type"];
	//std::cout << s<<std::endl;
	//pathparse.rootParse(config);
	//std::cout << "protocol:" << pathparse.methodParams["protocol"] << std::endl;
	//std::cout << "address:" << pathparse.methodParams["address"] << std::endl;
	//std::cout << "port:" << pathparse.methodParams["port"] << std::endl;
	//std::cout << pathparse.methodName.first << std::endl;
	//std::cout << pathparse.methodName.second << std::endl;
	//for (std::map<std::string, std::string>::iterator it = pathparse.idPath.begin(); it != pathparse.idPath.end(); it++) {
	//	std::cout << it->first << std::endl;
	//	std::cout << it->second << std::endl;
	//}
		
	OPCUAAdapter opcuaAdapter;
	opcuaAdapter.init();
	
	//MTConnectAdapter mtconnectAdapter;
	//mtconnectAdapter.init();

	//while (1) {

	//}
	
	return 0;
}
