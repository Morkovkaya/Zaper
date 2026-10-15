using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Collections.Generic;
using System.IO.Compression;
using System.Threading;
using System.Threading.Tasks;
using System.Diagnostics;
using System.Security.Principal;
using Microsoft.Win32;
namespace ZapretManager {
public class UiPreferences {public bool StartInTray,PanelAutoStart;public bool NotifyErrors=true;}
public class SavedProfile {public string Name;public Settings Settings;public string[] Applications;public bool ExclusionsEnabled;}
public static class Convenience {
 public static string LaunchTaskName="Zapret2Manager-"+WindowsIdentity.GetCurrent().User.Value;
 public static void SaveLaunchSettings(UiPreferences preferences,bool autoStart){
  Core.Guard();var oldPreferences=Preferences();var settings=Core.Load();bool original=settings.AutoStart;uint? originalStart=null;
  using(var key=Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\"+Core.Service)){if(key!=null)originalStart=Convert.ToUInt32(key.GetValue("Start",3));}
  try{SavePreferences(preferences);if(originalStart.HasValue)Core.Startup(autoStart);if(original!=autoStart){settings.AutoStart=autoStart;Core.Write(Core.PathOf("manager-settings.json"),settings);}}
  catch{try{SavePreferences(oldPreferences);}catch{}if(originalStart.HasValue)try{Core.ConfigureService(Core.Service,start:originalStart.Value);}catch{}throw;}
 }
 public static UiPreferences Preferences(){try{return File.Exists(Core.PathOf("ui-preferences.json"))?Core.Read<UiPreferences>(Core.PathOf("ui-preferences.json")):new UiPreferences();}catch{return new UiPreferences();}}
 public static void SavePreferences(UiPreferences p){
  string name=LaunchTaskName;
  Type type=Type.GetTypeFromProgID("Schedule.Service");dynamic scheduler=Activator.CreateInstance(type);scheduler.Connect();dynamic folder=scheduler.GetFolder("\\");
  if(p.PanelAutoStart){dynamic task=scheduler.NewTask(0);task.RegistrationInfo.Description="Панель Zaper в системном трее";task.Principal.UserId=WindowsIdentity.GetCurrent().Name;task.Principal.LogonType=3;task.Principal.RunLevel=1;task.Settings.Enabled=true;task.Settings.DisallowStartIfOnBatteries=false;task.Settings.StopIfGoingOnBatteries=false;task.Settings.ExecutionTimeLimit="PT0S";dynamic trigger=task.Triggers.Create(9);trigger.UserId=WindowsIdentity.GetCurrent().Name;dynamic action=task.Actions.Create(0);action.Path=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"Zapret2Manager.exe");action.Arguments="--tray";action.WorkingDirectory=AppDomain.CurrentDomain.BaseDirectory;folder.RegisterTaskDefinition(name,task,6,WindowsIdentity.GetCurrent().Name,null,3,null);}
  else{try{folder.GetTask(name);folder.DeleteTask(name,0);}catch(FileNotFoundException){}catch(System.Runtime.InteropServices.COMException e){if(e.ErrorCode!=unchecked((int)0x80070002))throw;}}
  Core.Write(Core.PathOf("ui-preferences.json"),p);
 }
 public static async Task<string> Repair(CancellationToken token){
  Core.Guard();var backup=File.Exists(Core.PathOf("config.txt"))&&File.Exists(Core.PathOf("manager-base.txt"))?Core.Backup():null;
  bool running=Core.State()=="Running";string archive=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"repair-runtime.zip");
  if(!File.Exists(archive))throw new FileNotFoundException("Встроенная копия восстановления отсутствует. Запустите полный установщик.");
  var changed=new List<string>();
  try{
   using(var zip=ZipFile.OpenRead(archive)){
    var manifestEntry=zip.GetEntry("runtime-sha256.json");if(manifestEntry==null)throw new Exception("В копии восстановления нет контрольных сумм");
    Dictionary<string,string> hashes;using(var reader=new StreamReader(manifestEntry.Open()))hashes=new System.Web.Script.Serialization.JavaScriptSerializer().Deserialize<Dictionary<string,string>>(reader.ReadToEnd());
    // Verify the archive before stopping or changing any runtime files.
    foreach(var item in zip.Entries)SafeDestination(Core.Root,item.FullName);
    foreach(var h in hashes){var entry=zip.GetEntry(h.Key.Replace('\\','/'));if(entry==null)throw new Exception("Копия восстановления неполная: "+h.Key);using(var sha=System.Security.Cryptography.SHA256.Create())using(var stream=entry.Open()){if(BitConverter.ToString(sha.ComputeHash(stream)).Replace("-","")!=h.Value)throw new Exception("Повреждена копия восстановления: "+h.Key);}}
    if(Core.State()!="NotInstalled")Core.Control("Off");else Exclusions.Stop();
    foreach(var entry in zip.Entries){token.ThrowIfCancellationRequested();if(string.IsNullOrEmpty(entry.Name))continue;string destination=SafeDestination(Core.Root,entry.FullName);bool immutable=hashes.ContainsKey(entry.FullName.Replace('/','\\'))||entry.FullName=="runtime-sha256.json";
     if(!immutable&&File.Exists(destination))continue;
     if(File.Exists(destination)){using(var a=entry.Open())using(var b=File.OpenRead(destination))using(var sha=System.Security.Cryptography.SHA256.Create()){if(sha.ComputeHash(a).SequenceEqual(sha.ComputeHash(b)))continue;}}
     Directory.CreateDirectory(Path.GetDirectoryName(destination));entry.ExtractToFile(destination,true);changed.Add(entry.FullName);
    }
   }
   Core.Preflight();var text=Core.Build(Core.Load());await Core.Validate(text,token);File.WriteAllText(Core.PathOf("config.txt"),text+"\r\n",Encoding.ASCII);
   await Exclusions.Ensure();
   if(Core.State()=="NotInstalled")await Core.Install(token);else if(running)Core.Control("On");
   return "Проверка пройдена. Восстановлено файлов: "+changed.Count+". Конфигурация проверена, службы настроены. "+(backup==null?"":"Копия настроек сохранена в истории.");
  }catch{if(running&&Core.State()!="Running"){try{Core.Control("On");}catch{}}throw;}
 }
 public static string SafeDestination(string root,string relative){string prefix=Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar;string full=Path.GetFullPath(Path.Combine(root,relative.Replace('/',Path.DirectorySeparatorChar)));if(!full.StartsWith(prefix,StringComparison.OrdinalIgnoreCase))throw new Exception("Недопустимый путь в архиве");return full;}
 public static string Redact(string text){
  text=text.Replace(Core.Root,"[INSTALL]");text=Regex.Replace(text,@"(?i)[A-Z]:\\Users\\[^\\\s""<>]+","[USER]");
  text=Regex.Replace(text,@"(?im)(authorization\s*:\s*)[^\r\n]+","$1[REDACTED]");
  return Regex.Replace(text,@"(?i)((?:password|passwd|secret|token|api[_-]?key)\s*[""']?\s*[=:]\s*)(?:""[^""\r\n]*""|[^\s,;]+)","$1[REDACTED]");
 }
 public static void ExportDiagnostics(string file){
  using(var stream=new FileStream(file,FileMode.Create,FileAccess.ReadWrite,FileShare.None))using(var zip=new ZipArchive(stream,ZipArchiveMode.Create)){
   Add(zip,"summary.txt","Zaper "+System.Reflection.Assembly.GetExecutingAssembly().GetName().Version+"\r\nUTC: "+DateTime.UtcNow.ToString("o")+"\r\nСлужба: "+Core.State()+"\r\nИсключения: "+Exclusions.State()+"\r\n"+Core.Context());
   foreach(string name in new[]{"config.txt","manager-settings.json","zapret2-engine-status.json","app-exclusions-status.json"})if(File.Exists(Core.PathOf(name)))Add(zip,name,File.ReadAllText(Core.PathOf(name)));
   var c=Exclusions.Load();Add(zip,"excluded-applications.txt",string.Join("\r\n",(c.Applications??new string[0]).Select(Path.GetFileName)));
   foreach(string name in new[]{"native-manager.log","engine-service.log","exclusions-service.log"})if(File.Exists(Core.PathOf(name)))Add(zip,name,string.Join("\r\n",File.ReadLines(Core.PathOf(name)).Reverse().Take(300).Reverse()));
  }
 }
 static void Add(ZipArchive zip,string name,string value){using(var writer=new StreamWriter(zip.CreateEntry(name).Open(),new UTF8Encoding(false)))writer.Write(Redact(value));}
 public static string[] History(){string root=Core.PathOf("native-backups");return Directory.Exists(root)?Directory.GetDirectories(root).Where(d=>File.Exists(Path.Combine(d,"native-manifest.json"))).OrderByDescending(d=>Path.GetFileName(d)).ToArray():new string[0];}
 public static async Task RestoreHistory(string directory,CancellationToken token){
  Core.Guard();string full=SafeDestination(Core.Root,"native-backups/"+Path.GetFileName(directory));if(!string.Equals(Path.GetFullPath(directory),full,StringComparison.OrdinalIgnoreCase))throw new Exception("Недопустимая копия");
  var settings=Core.Read<Settings>(Path.Combine(full,"manager-settings.json"));await Core.Validate(Core.Build(settings,File.ReadAllText(Path.Combine(full,"manager-base.txt"))),token);
  var current=Core.Backup();try{Core.Restore(Core.Read<Snapshot>(Path.Combine(full,"native-manifest.json")));}catch{Core.Restore(current);throw;}
 }
 public static SavedProfile Profile(string name){var c=Exclusions.Load();return new SavedProfile {Name=name,Settings=Core.Load(),Applications=c.Applications,ExclusionsEnabled=c.Enabled};}
 public static Settings Preset(bool gaming){var s=Core.Load();s.Game=gaming?"udp":"off";s.IPSet="loaded";s.GameUdpPreset=gaming?"alt12-exp":"native";s.FaceitServerExclusions=!gaming;return s;}
 public static async Task<string> ImportProfile(SavedProfile p,CancellationToken token){
  if(p==null||p.Settings==null)throw new Exception("Не найден профиль настроек");await Core.Validate(Core.Build(p.Settings),token);var previous=Core.Backup();var old=Exclusions.Load();
  string[] apps=(p.Applications??new string[0]).Select(Exclusions.Normalize).Where(File.Exists).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
  try{await Core.Apply(p.Settings,token);await Exclusions.Save(new ExclusionConfig {Enabled=p.ExclusionsEnabled,Applications=apps});}catch{Core.Restore(previous);Exclusions.Save(old).GetAwaiter().GetResult();throw;}
  return "Профиль применён. Приложений в исключениях: "+apps.Length+". Не найдено EXE на этом ПК: "+((p.Applications??new string[0]).Length-apps.Length);
 }
}
}
