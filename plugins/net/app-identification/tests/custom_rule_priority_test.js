// SPDX-License-Identifier: BSD-2-Clause
// Run with node. Evaluate the real flow-view functions without browser scaffolding.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(__dirname + '/../src/opnsense/mvc/app/views/OPNsense/AppIdentification/flows.volt', 'utf8');
const names = ['normalizeDomain', 'domainRuleMatches', 'domainSpecificity', 'ipv4ToNumber', 'ipInCidr', 'splitRuleMatchValues', 'matchCustomRule'];
const functions = names.map(name => {
    const start = source.indexOf('\t\tfunction ' + name + '(');
    assert(start >= 0, 'Missing production function: ' + name);
    const end = source.indexOf('\n\t\tfunction ', start + 1);
    return source.slice(start, end);
}).join('\n');
const context = vm.createContext({URL, customApplicationRules: [
    {match_type:'domain', match_value:'qq.com\nvery.deep.unrelated.example.invalid', app_label:'Broad'},
    {match_type:'domain', match_value:'work.weixin.qq.com\nwecom.qq.com', app_label:'Specific'},
    {match_type:'domain', match_value:'work.weixin.qq.com\nother.invalid', app_label:'Later tie'},
    {match_type:'port', match_value:'443', app_label:'Port fallback'}
]});
vm.runInContext(functions, context);
for (const [host, label] of Object.entries({
    'work.weixin.qq.com':'Specific', 'sub.work.weixin.qq.com':'Specific',
    'wecom.qq.com':'Specific', 'other.qq.com':'Broad',
    'notqq.com':'Port fallback', 'qq.com.attacker.invalid':'Port fallback'
})) {
    context.row = {server_name:host, server_port:443};
    assert.equal(vm.runInContext('matchCustomRule(row).app_label', context), label, host);
}
console.log('PASS: flow view uses the matched domain, stable ties and port fallback');
