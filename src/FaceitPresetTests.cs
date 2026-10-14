using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Collections.Generic;
namespace ZapretManager {
public static class FaceitPresetTests {
 public static async Task<int> Run(string report){var lines=new List<string>();int failures=0;Action<bool,string> check=(ok,name)=>{lines.Add((ok?"PASS: ":"FAIL: ")+name);if(!ok)failures++;};string exclude=Core.PathOf("files\\faceit-game-exclude.txt");byte[] old=File.Exists(exclude)?File.ReadAllBytes(exclude):null;try{
  using(var sha=System.Security.Cryptography.SHA256.Create())using(var file=File.OpenRead(Core.PathOf("files\\faceit_legacy_udp.bin")))check(BitConverter.ToString(sha.ComputeHash(file)).Replace("-","")=="E065870CB0D13152E6132807BBF42218A9E7CD8D96F5602B61674CC540F3A56E","game blob matches supplied working ALT12 ACTIVE_GAME and EXP 4pda blobs");
  var s=Core.Load();s.Game="udp";s.IPSet="loaded";s.FaceitServerExclusions=false;s.GameUdpPreset="native";string native=Core.Build(s);s.GameUdpPreset="alt12-exp";string compat=Core.Build(s);
  check(!compat.Substring(compat.LastIndexOf("--new",StringComparison.Ordinal)).Contains("--hostlist"),"game UDP has no hostname filters: unknown game packets can select their IPSet profile");
  check(compat.Substring(compat.LastIndexOf("--new",StringComparison.Ordinal)).Contains("--out-range=<n4")&&!compat.Substring(compat.LastIndexOf("--new",StringComparison.Ordinal)).Contains("--out-range=-n4 --payload=all"),"legacy cutoff n4 maps to exclusive upper bound: first three game packets");check(compat.Contains("--lua-desync=fake:blob=faceit_legacy_udp:repeats=10:payload=unknown"),"ALT12/EXP unknown UDP gets ten copies of the original shared blob");
  string prefix=native.Substring(0,native.LastIndexOf("--new",StringComparison.Ordinal));string otherPrefix=compat.Substring(compat.IndexOf('\n')+1);otherPrefix=otherPrefix.Substring(0,otherPrefix.LastIndexOf("--new",StringComparison.Ordinal));check(prefix==otherPrefix,"TCP, Discord and QUIC profiles are unchanged by compatibility mode");
  File.WriteAllText(exclude,"51.75.54.238\r\n",Encoding.ASCII);s.FaceitServerExclusions=false;check(!Core.Build(s).Contains("faceit-game-exclude.txt"),"compatibility can disable saved FACEIT IP exclusions without deleting them");s.FaceitServerExclusions=true;check(Core.Build(s).Contains("faceit-game-exclude.txt"),"manual FACEIT IP exclusions can be explicitly re-enabled");
  foreach(string game in new[]{"off","udp","tcp","all"})foreach(string scope in new[]{"none","loaded","any"}){s.Game=game;s.IPSet=scope;await Core.Validate(Core.Build(s),CancellationToken.None);check(true,"winws2 accepts compatible mode "+game+"/"+scope);}
 }catch(Exception e){check(false,e.ToString());}finally{if(old==null){if(File.Exists(exclude))File.Delete(exclude);}else File.WriteAllBytes(exclude,old);}lines.Add("Failures: "+failures);File.WriteAllLines(report,lines);return failures==0?0:1;
 }
}
}
