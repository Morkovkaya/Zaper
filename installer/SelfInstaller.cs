using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Diagnostics;
using System.Security.Principal;
using System.ServiceProcess;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("Zaper Setup")]
[assembly: AssemblyDescription("Zaper self-contained installer")]
[assembly: AssemblyCompany("Zapret 2 Manager Community")]
[assembly: AssemblyProduct("Zaper")]
[assembly: AssemblyVersion("3.8.2.0")]
[assembly: AssemblyFileVersion("3.8.2.0")]

namespace ZaperSetup {
static class Program {
 [STAThread] static int Main(string[] args) {
  string log=Path.Combine(Path.GetTempPath(),"Zaper-Setup-error.txt");
  try {
   bool test=args.Any(a=>a.Equals("/TEST",StringComparison.OrdinalIgnoreCase));
   string target=test?Argument(args,"/DIR="):Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),"zapret2");
   if(String.IsNullOrWhiteSpace(target))throw new Exception("Укажите /DIR=папка для тестовой установки.");
   target=Path.GetFullPath(target);
   bool installService=!args.Any(a=>a.Equals("/NOSERVICE",StringComparison.OrdinalIgnoreCase));
   bool desktop=!args.Any(a=>a.Equals("/NODESKTOP",StringComparison.OrdinalIgnoreCase));
   if(!test&&!new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator)){
    Process.Start(new ProcessStartInfo(Assembly.GetExecutingAssembly().Location){UseShellExecute=true,Verb="runas",Arguments=String.Join(" ",args.Select(Quote))});
    return 0;
   }
   string temp=Path.Combine(Path.GetTempPath(),"ZaperSetup-"+Guid.NewGuid().ToString("N"));
   try {
    Directory.CreateDirectory(temp);
    ExtractPayload(Assembly.GetExecutingAssembly().Location,temp);
    File.Delete(Path.Combine(temp,"payload.zip"));
    bool resume=PrepareTarget(target,test);
    CopyPayload(temp,target);
    Configure(target,installService,test);
    if(!test) {
     if(desktop)CreateShortcut(target);
     Launch(target);
    }
    return 0;
   } finally {try{Directory.Delete(temp,true);}catch{}}
  } catch(Exception e) {
   try{File.WriteAllText(log,e.ToString());}catch{}
   MessageBox.Show(e.Message+Environment.NewLine+"Подробности: "+log,"Zaper — ошибка установки",MessageBoxButtons.OK,MessageBoxIcon.Error);
   return 1;
  }
 }
 static string Argument(string[] args,string prefix){var value=args.FirstOrDefault(a=>a.StartsWith(prefix,StringComparison.OrdinalIgnoreCase));return value==null?"":value.Substring(prefix.Length).Trim('"');}
 static string Quote(string value){return "\""+value.Replace("\"","\\\"")+"\"";}
 static void ExtractPayload(string installer,string directory){
  long length=new FileInfo(installer).Length;if(length<8)throw new Exception("Повреждённый файл установщика.");
  byte[] marker;using(var input=new FileStream(installer,FileMode.Open,FileAccess.Read,FileShare.Read)){input.Seek(-8,SeekOrigin.End);marker=new byte[8];ReadAll(input,marker,8);}
  long zipLength=BitConverter.ToInt64(marker,0);if(zipLength<=0||zipLength>length-8)throw new Exception("В установщике не найден пакет Zaper.");
  string zip=Path.Combine(directory,"payload.zip");
  using(var input=new FileStream(installer,FileMode.Open,FileAccess.Read,FileShare.Read))using(var output=new FileStream(zip,FileMode.Create,FileAccess.Write,FileShare.None)){
   input.Seek(length-8-zipLength,SeekOrigin.Begin);byte[] buffer=new byte[1024*1024];int read;long remaining=zipLength;while(remaining>0&&(read=input.Read(buffer,0,(int)Math.Min(buffer.Length,remaining)))>0){output.Write(buffer,0,read);remaining-=read;}
  }
  string root=Path.GetFullPath(directory)+Path.DirectorySeparatorChar;
  using(var archive=ZipFile.OpenRead(zip))foreach(var entry in archive.Entries){
   string destination=Path.GetFullPath(Path.Combine(directory,entry.FullName));
   if(!destination.StartsWith(root,StringComparison.OrdinalIgnoreCase))throw new Exception("Недопустимый путь в пакете: "+entry.FullName);
   if(entry.FullName.EndsWith("/",StringComparison.Ordinal)||entry.FullName.EndsWith("\\",StringComparison.Ordinal)){Directory.CreateDirectory(destination);continue;}
   Directory.CreateDirectory(Path.GetDirectoryName(destination));
   using(var input=entry.Open())using(var output=new FileStream(destination,FileMode.Create,FileAccess.Write,FileShare.None))input.CopyTo(output);
  }
 }
 static void ReadAll(Stream stream,byte[] buffer,int length){int offset=0;while(offset<length){int read=stream.Read(buffer,offset,length-offset);if(read<=0)throw new EndOfStreamException();offset+=read;}}
 static bool PrepareTarget(string target,bool test){
  Directory.CreateDirectory(target);
  bool resume=false;
  if(!test){
   foreach(var process in Process.GetProcessesByName("Zapret2Manager"))try{process.Kill();}catch{}
   foreach(var name in new[]{"zapret2","zapret2-exclusions"})try{using(var service=new ServiceController(name)){service.Refresh();if(service.Status==ServiceControllerStatus.Running){resume=true;service.Stop();service.WaitForStatus(ServiceControllerStatus.Stopped,TimeSpan.FromSeconds(20));}}}catch{}
   foreach(var process in Process.GetProcessesByName("Zapret2Service"))try{process.Kill();}catch{}
  }
  File.WriteAllText(Path.Combine(target,"package-upgrade-state.json"),resume?"true":"false");
  return resume;
 }
 static bool AlwaysReplace(string relative){return relative.StartsWith("app\\",StringComparison.OrdinalIgnoreCase)||relative.StartsWith("licenses\\",StringComparison.OrdinalIgnoreCase)||relative.Equals("runtime-sha256.json",StringComparison.OrdinalIgnoreCase)||relative.Equals("manager-base.template",StringComparison.OrdinalIgnoreCase);}
 static bool ProtectedRuntime(string relative){return relative.Equals("winws2.exe",StringComparison.OrdinalIgnoreCase)||relative.Equals("cygwin1.dll",StringComparison.OrdinalIgnoreCase)||relative.Equals("WinDivert.dll",StringComparison.OrdinalIgnoreCase)||relative.Equals("WinDivert64.sys",StringComparison.OrdinalIgnoreCase)||relative.StartsWith("files\\",StringComparison.OrdinalIgnoreCase)||relative.StartsWith("lua\\",StringComparison.OrdinalIgnoreCase)||relative.StartsWith("http3\\",StringComparison.OrdinalIgnoreCase)||relative.StartsWith("windivert.filter\\",StringComparison.OrdinalIgnoreCase)||relative.StartsWith("lists\\",StringComparison.OrdinalIgnoreCase);}
 static void CopyPayload(string source,string target){
  string manifestPath=Path.Combine(source,"runtime-sha256.json");var hashes=new System.Web.Script.Serialization.JavaScriptSerializer().Deserialize<System.Collections.Generic.Dictionary<string,string>>(File.ReadAllText(manifestPath));
  CopyDirectory(source,target,source,target,hashes);
 }
 static void CopyDirectory(string source,string target,string sourceRoot,string targetRoot,System.Collections.Generic.Dictionary<string,string> hashes){
  Directory.CreateDirectory(target);
  foreach(string directory in Directory.GetDirectories(source)){
   string relative=Path.Combine(DirectoryRelative(sourceRoot,directory),"x").TrimEnd('x').TrimEnd('\\');
   CopyDirectory(directory,Path.Combine(targetRoot,relative),sourceRoot,targetRoot,hashes);
  }
  foreach(string file in Directory.GetFiles(source)){
   string relative=FileRelative(sourceRoot,file);string destination=Path.Combine(targetRoot,relative);Directory.CreateDirectory(Path.GetDirectoryName(destination));
   bool replace=AlwaysReplace(relative)||!File.Exists(destination);
   string expected;if(!replace&&ProtectedRuntime(relative)&&(hashes.TryGetValue(relative,out expected)||hashes.TryGetValue(relative.Replace('\\','/'),out expected))){using(var sha=System.Security.Cryptography.SHA256.Create())using(var stream=File.OpenRead(destination)){string actual=BitConverter.ToString(sha.ComputeHash(stream)).Replace("-","");replace=!actual.Equals(expected,StringComparison.OrdinalIgnoreCase);}}
   if(replace)File.Copy(file,destination,true);
  }
 }
 static string DirectoryRelative(string root,string directory){string value=directory.Substring(root.Length).TrimStart(Path.DirectorySeparatorChar);return value.EndsWith("\\")?value:value+"\\";}
 static string FileRelative(string root,string file){return file.Substring(root.Length).TrimStart(Path.DirectorySeparatorChar);}
 static void Configure(string target,bool installService,bool test){
  string app=Path.Combine(target,"app","Zapret2Manager.exe");string arguments="--configure-package";if(installService&&!test)arguments+=" --install-service";
  var start=new ProcessStartInfo(app,arguments){UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true,WorkingDirectory=Path.GetDirectoryName(app)};
  using(var process=Process.Start(start)){
   string output=process.StandardOutput.ReadToEnd(),error=process.StandardError.ReadToEnd();
   if(!process.WaitForExit(180000))try{process.Kill();}catch{}
   if(process.ExitCode!=0){string details=Path.Combine(target,"package-error.txt");string extra=File.Exists(details)?File.ReadAllText(details):output+error;throw new Exception("Не удалось проверить конфигурацию Zaper."+(extra==""?"":Environment.NewLine+extra));}
  }
 }
 static void CreateShortcut(string target){
  string desktop=Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
  foreach(string old in new[]{"Управление zapret 2.lnk","zaper.lnk"})try{File.Delete(Path.Combine(desktop,old));}catch{}
  string link=Path.Combine(desktop,"Zaper.lnk");string app=Path.Combine(target,"app","Zapret2Manager.exe");
  Type type=Type.GetTypeFromProgID("WScript.Shell");if(type==null)return;object shell=Activator.CreateInstance(type);object shortcut=type.InvokeMember("CreateShortcut",BindingFlags.InvokeMethod,null,shell,new object[]{link});
  shortcut.GetType().InvokeMember("TargetPath",BindingFlags.SetProperty,null,shortcut,new object[]{app});
  shortcut.GetType().InvokeMember("WorkingDirectory",BindingFlags.SetProperty,null,shortcut,new object[]{Path.GetDirectoryName(app)});
  shortcut.GetType().InvokeMember("IconLocation",BindingFlags.SetProperty,null,shortcut,new object[]{app+",0"});
  shortcut.GetType().InvokeMember("Save",BindingFlags.InvokeMethod,null,shortcut,null);
 }
 static void Launch(string target){Process.Start(new ProcessStartInfo(Path.Combine(target,"app","Zapret2Manager.exe")){UseShellExecute=true,WorkingDirectory=Path.Combine(target,"app")});}
}
}
