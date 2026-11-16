#pragma once
#include <nlohmann/json.hpp> 
#include <pugixml/pugixml.hpp>
#include <string>

namespace utils
{
    nlohmann::json parseStreams(std::string data);
    std::string getTimeStamp();
}
