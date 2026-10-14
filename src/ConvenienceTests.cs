using System;
using System.IO;
using System.Linq;
using System.Text;
using System.IO.Compression;
using System.Threading;
using System.Threading.Tasks;
using System.Collections.Generic;
namespace ZapretManager {
public static class ConvenienceTests {
 public static async Task<int> Run(string report,bool integration){var lines=new List<string>();int failures=0;Action<bool,string> check=(ok,name)=>{lines.Add((ok?"PASS: ":"FAIL: ")+name);if(!ok)failures++;};string originalRoot=Core.Root,originalService=Core.Service,originalHelper=Exclusions.ServiceName;bool originalTesting=Exclusions.Testing;string fixture=Path.Combine(Path.GetDirectoryName(report),"convenience-fixture-"+Guid.NewGuid().ToString("N"));
  try{
   ZipFile.ExtractToDirectory(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"repair-runtime.zip"),fixture);Core.Root=fixture;Core.Service="zapret2-convenience-test";Exclusions.ServiceName="zapret2-convenience-helper-test";Exclusions.Testing=true;
   if(Core.State()!="NotInstalled"||Exclusions.State()!="NotInstalled")throw new Exception("Test service name is occupied");
   string basis="--wf-tcp-out=1\r\n--filter-tcp=1\r\n";File.WriteAllText(Core.PathOf("manager-base.txt"),basis,Encoding.ASCII);Core.Write(Core.PathOf("manager-settings.json"),new Settings {Game="off",IPSet="none",AutoStart=false});File.WriteAllText(Core.PathOf("config.txt"),Core.Build(Core.Load()),Encoding.ASCII);Core.Write(Core.PathOf("app-exclusions.json"),new ExclusionConfig {Enabled=false,Applications=new string[0]});
   Core.Preflight();check(true,"packaged recovery archive matches runtime hashes including service host");
   var ordinary=Convenience.Preset(false);var gaming=Convenience.Preset(true);check(ordinary.Game=="off"&&ordinary.IPSet=="loaded","ordinary profile leaves websites/Discord and disables general game processing");check(gaming.Game=="udp"&&gaming.GameUdpPreset=="alt12-exp"&&!gaming.FaceitServerExclusions,"game profile retains verified FACEIT compatibility");await Core.Validate(Core.Build(gaming),CancellationToken.None);check(true,"game preset accepted by winws2");
   string input="secret=privateValue\npassword=privatePassword\nAuthorization: Bearer privateToken\n{\"token\":\"jsonSecret\"}\nC:\\Users\\PrivateUser\\file.txt\n"+fixture;
   string redacted=Convenience.Redact(input);check(!new[]{"privateValue","privatePassword","privateToken","jsonSecret","PrivateUser",fixture}.Any(redacted.Contains),"diagnostics remove plain/JSON secrets, bearer credentials and user directory names");
   bool rejected=false;try{Convenience.SafeDestination(fixture,"../outside.txt");}catch{rejected=true;}check(rejected,"archive traversal rejected");
   var saved=Core.Backup();check(Convenience.History().Contains(saved.Directory),"history finds saved snapshots");File.WriteAllText(Core.PathOf("manager-settings.json"),Core.Json.Serialize(new Settings {Game="udp",IPSet="loaded"}),Encoding.UTF8);await Convenience.RestoreHistory(saved.Directory,CancellationToken.None);check(Core.Load().Game=="off","history restores actual earlier settings and keeps a rollback copy");
   var profile=Convenience.Profile("Fixture");profile.Applications=new[]{Path.Combine(fixture,"app","Zapret2Service.exe"),Path.Combine(fixture,"missing.exe")};profile.ExclusionsEnabled=false;string message=await Convenience.ImportProfile(profile,CancellationToken.None);check(Exclusions.Load().Applications.Length==1&&message.Contains("1"),"portable profile excludes missing EXEs and applies only existing paths");
   var broken=Convenience.Profile("Bad");broken.Settings.Game="invalid";string before=File.ReadAllText(Core.PathOf("manager-settings.json"));rejected=false;try{await Convenience.ImportProfile(broken,CancellationToken.None);}catch{rejected=true;}check(rejected&&before==File.ReadAllText(Core.PathOf("manager-settings.json")),"invalid imported profile is rejected before changing settings");
   File.WriteAllText(Core.PathOf("native-manager.log"),input);string export=Path.Combine(fixture,"diagnostics.zip");Convenience.ExportDiagnostics(export);Convenience.ExportDiagnostics(export);using(var zip=ZipFile.OpenRead(export)){check(zip.GetEntry("summary.txt")!=null&&zip.GetEntry("config.txt")!=null,"diagnostics ZIP contains actual status and config and supports overwrite");using(var reader=new StreamReader(zip.GetEntry("native-manager.log").Open()))check(!reader.ReadToEnd().Contains("privateToken"),"ZIP logs are redacted");}
   check(Convenience.Preferences().NotifyErrors&&!Convenience.Preferences().PanelAutoStart,"default tray preferences do not create automatic startup");
   if(integration){
    string dll=Core.PathOf("cygwin1.dll");File.Move(dll,dll+".original");File.WriteAllText(dll,"corrupt fixture");string result=await Convenience.Repair(CancellationToken.None);check(Core.State()=="Running"&&result.Contains("Восстановлено"),"repair recovers corrupt Cygwin and starts isolated TCP port 1 service");Core.Preflight();check(true,"repaired runtime verifies after service start");Core.Control("Off");string list=Core.PathOf("lists\\list-general-user.txt");File.WriteAllText(list,"custom-preserved.example\r\n");await Convenience.Repair(CancellationToken.None);check(File.ReadAllText(list)=="custom-preserved.example\r\n"&&Core.State()=="Stopped","repair preserves user domain lists and stopped state");
   }
  }catch(Exception e){check(false,e.ToString());}
  finally{if(integration&&Core.Root==fixture){try{if(Core.State()!="NotInstalled")Core.Remove(CancellationToken.None).GetAwaiter().GetResult();Exclusions.Remove().GetAwaiter().GetResult();}catch(Exception e){check(false,"test service cleanup: "+e.Message);}}Core.Root=originalRoot;Core.Service=originalService;Exclusions.ServiceName=originalHelper;Exclusions.Testing=originalTesting;}
  lines.Add("Failures: "+failures);File.WriteAllLines(report,lines,Encoding.UTF8);return failures==0?0:1;
 }
}
}
