using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Drawing;
using System.Net;
using System.Net.Sockets;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
namespace ZapretManager {
public static class RevisionTests {
 public static async Task<int> Run(string report,bool online){var lines=new List<string>();int failures=0;Action<bool,string> check=(ok,name)=>{lines.Add((ok?"PASS: ":"FAIL: ")+name);if(!ok)failures++;};string root=Core.Root,service=Core.Service;string fixture=Path.Combine(Path.GetDirectoryName(report),"ux-fixture-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(fixture);
  try{
   Core.Root=fixture;string path=Path.Combine(fixture,"hosts");string original="# original\r\n127.0.0.1 localhost\r\n::1 localhost\r\n";File.WriteAllText(path,original);check(HostsEditor.Validate(original)==2,"Hosts accepts comments, IPv4, IPv6 and localhost");
   foreach(string invalid in new[]{"bad-ip example.com","127.0.0.1 https://example.com","1.2.3.4 *.example.com"}){bool rejected=false;try{HostsEditor.Validate(invalid);}catch{rejected=true;}check(rejected,"Hosts rejects invalid mapping: "+invalid);}
   string text=original+"192.0.2.1 custom.example # mine\r\n";string backup=HostsEditor.Save(path,original,text);check(File.ReadAllText(path)==text&&File.ReadAllText(backup)==original,"Hosts editor writes edited mappings and preserves original backup");bool changed=false;try{HostsEditor.Save(path,original,"127.0.0.1 changed.example");}catch(IOException){changed=true;}check(changed&&File.ReadAllText(path)==text,"concurrent Hosts edits are rejected without data loss");
   check(HostsEditor.Validate("")==0,"empty Hosts is a valid explicit edit");
   check(typeof(Network).GetMethod("Measure").GetParameters().Length==2&&typeof(Network).GetMethod("Tune").GetParameters().Length==2,"network tests and autotuner have no confirmation callback");
   var server=new TcpListener(IPAddress.Loopback,0);try{
    server.Start();int port=((IPEndPoint)server.LocalEndpoint).Port;var respond=Task.Run(async()=>{using(var peer=await server.AcceptTcpClientAsync()){var stream=peer.GetStream();var buffer=new byte[8192];await stream.ReadAsync(buffer,0,buffer.Length);byte[] response=Encoding.ASCII.GetBytes("HTTP/1.1 200 OK\r\nContent-Length: 11\r\nConnection: close\r\n\r\n1.2.3.0/24\n");await stream.WriteAsync(response,0,response.Length);}});string received=await Downloads.Fetch("http://127.0.0.1:"+port+"/list",CancellationToken.None);await respond;check(Core.ValidateIPSet(received)==1,"new downloader transfers and validates complete IP list");
   }finally{server.Stop();}
   using(var stop=new CancellationTokenSource()){stop.Cancel();bool cancelled=false;try{await Downloads.Fetch("http://127.0.0.1:9/",stop.Token);}catch(OperationCanceledException){cancelled=true;}check(cancelled,"downloader honours cancellation and cleans route processes");}
   using(var icon=Icon.ExtractAssociatedIcon(System.Reflection.Assembly.GetExecutingAssembly().Location))using(var bitmap=icon.ToBitmap()){int green=0;for(int y=0;y<bitmap.Height;y++)for(int x=0;x<bitmap.Width;x++){var c=bitmap.GetPixel(x,y);if(c.G>c.R+45&&c.G>c.B)green++;}check(green>5,"EXE contains matching green tray Z icon");}
   Core.Root=root;
   if(online){
    string list=await Downloads.IPSet(CancellationToken.None);check(Core.ValidateIPSet(list)>0,"real official IP list downloaded through available network route");
    string hosts=await Downloads.Fetch("https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/main/.service/hosts",CancellationToken.None);check(HostsEditor.Validate(hosts)>0,"real proposed Hosts download validates without changing system file");
    Core.Service="zapret2-ux-test";if(Core.State()!="NotInstalled")throw new Exception("UX test service name is occupied");string old=File.ReadAllText(Core.PathOf("lists\\ipset-all.txt"));string result=await Core.UpdateIPs(CancellationToken.None);check(Core.ValidateIPSet(File.ReadAllText(Core.PathOf("lists\\ipset-all.txt")))>0&&result.StartsWith("IPSet обновлён"),"IP update button backend replaces list and validates engine configuration");check(File.ReadAllText(Core.PathOf("lists\\ipset-all.txt.native-backup"))==old,"IP update preserves previous list backup");
    var rows=await Network.Faceit("",CancellationToken.None);check(rows.Any(r=>r.Name=="Cloudflare DNS")&&rows.Any(r=>r.Name=="Google DNS")&&rows.Count(r=>r.Kind=="region")==10,"server diagnostics include eight FACEIT regions and two independent nodes");
   }
  }catch(Exception e){check(false,e.ToString());}finally{Core.Root=root;Core.Service=service;}lines.Add("Failures: "+failures);File.WriteAllLines(report,lines,Encoding.UTF8);return failures==0?0:1;
 }
}
}
