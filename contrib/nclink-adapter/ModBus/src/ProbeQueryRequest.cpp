#include "ProbeQueryRequest.h"
#include <nlohmann/json.hpp>
#include <fstream>


ProbeQueryRequest::ProbeQueryRequest() {}

std::string ProbeQueryRequest::process(std::string requestData)
{
	//�յ���json�ļ������,��ô���
	nlohmann::json requestJsonData = nlohmann::json::parse(requestData);
	nlohmann::json responseJsonData;

	responseJsonData["@id"] = requestJsonData["@id"];
	responseJsonData["code"] = "OK";
	std::ifstream file("conf/ModbusModel.json");
	nlohmann::ordered_json config = nlohmann::ordered_json::parse(file);
	responseJsonData["probe"] = config;
	file.close();
	return responseJsonData.dump(1);
}