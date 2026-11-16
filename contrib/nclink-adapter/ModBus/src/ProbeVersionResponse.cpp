#include "ProbeVersionResponse.h"
#include <nlohmann/json.hpp>
#include <fstream>
ProbeVersionResponse::ProbeVersionResponse() {}
//requestdata {\"@id\": \"some_mid_001\",\"guid\" : \"dev_uuid\",\"version\" : \"v1.0.1\",\"privateInfo\" : null}"
std::string ProbeVersionResponse::process(std::string requestData)
{
	nlohmann::json requestJsonData = nlohmann::json::parse(requestData);
	nlohmann::json responseJsonData;
	responseJsonData["@id"] = requestJsonData["@id"];
	responseJsonData["guid"] = requestJsonData["guid"];

	std::fstream file("conf/ModbusModel.json");
	nlohmann::json modelJson = nlohmann::json::parse(file);
	responseJsonData["version"] = modelJson["version"];
	responseJsonData["privateInfo"] = requestJsonData["privateInfo"];
	file.clear();
	std::cout << modelJson.dump(1);
	if (file.is_open()) {
		//file << modelJson.dump(4); 
		;
	}
	else std::cout << "file is not open.\n";
	//这个也并并不需要返回内容，这个接口存疑
	return responseJsonData.dump(1);

}