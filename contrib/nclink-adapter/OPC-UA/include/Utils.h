#pragma once
#include <nlohmann/json.hpp>
#include <map>

namespace tools {
	class PathParse {
	public:
		void rootParse(nlohmann::json);
		/*用于映射NC-Link节点id与该id在模型文件中的位置
		* key:id
		* value示例:/devices/0/dataItems/0
		*/
		std::map<std::string, std::string> idPath;
		/*根对象下的方法对象，保存服务器地址等参数
		* key:参数名
		* value:参数值
		*/
		std::map<std::string, std::string> methodParams;
		/*用于映射NC-Link节点id与opc ua节点的身份特征
		* key:id
		* value:identity
		*/
		std::map<std::string, nlohmann::json> idIdentity;
		//测试用
		std::pair<std::string, std::string> methodName;
		std::vector<nlohmann::json> sampleChannel;
		/*采样节点集合
		*/
		std::vector<std::string> sampleId;

	private:
		void devicesParse(nlohmann::json deviceObject, nlohmann::json::json_pointer ptr);
		void componentsParse(nlohmann::json component, nlohmann::json::json_pointer ptr);
	};
	class TypeConversion {
	public:
		std::uint8_t* UINT8(std::string endianness, int rc, std::uint8_t* dest);
		std::uint16_t* UINT16(std::string endianness, int rc, std::uint8_t* dest);
		std::int16_t* INT16(std::string endianness, int rc, std::uint8_t* dest);
		std::uint32_t* UINT32(std::string endianness, int rc, std::uint8_t* dest);
		std::int32_t* INT32(std::string endianness, int rc, std::uint8_t* dest);
		std::uint64_t* UINT64(std::string endianness, int rc, std::uint8_t* dest);
		std::int64_t* INT64(std::string endianness, int rc, std::uint8_t* dest);
		float* FLOAT(std::string endianness, int rc, std::uint8_t* dest);
	};
	extern std::map<std::string, int> TypeConversionCode;
}
