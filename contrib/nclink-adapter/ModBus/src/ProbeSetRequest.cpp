#include "ProbeSetRequest.h"
#include <nlohmann/json.hpp>
#include <fstream>
#include <iostream>
#include <plog/Log.h>
ProbeSetRequest::ProbeSetRequest() {}
//requestdata "{\"@id\":\"123\",\"probe\":\"{...}\"}"

std::string ProbeSetRequest::process(std::string requestData)
{
	nlohmann::ordered_json requestJsonData;
	nlohmann::ordered_json responseJsonData;
	//����Ƿ�����json��ʽ�������ĺϷ��Լ��û����ɣ�����ṹ���⣩
	try {
		requestJsonData = nlohmann::json::parse(requestData);
	}
	catch (std::exception e) {
		std::cout << e.what() << std::endl;
		PLOG_DEBUG << e.what() << std::endl;
		//���ش���ԭ��
	}
	
	responseJsonData["@id"] = requestJsonData["@id"];
	std::fstream  modelFile;
	modelFile.open("conf/ModbusModel.json", std::ios::out);
	//ordered_json ����˳��
	modelFile << requestJsonData["probe"];
	responseJsonData["code"] = "OK";
	//���¼���
	modelFile.close();
	return responseJsonData.dump();

}