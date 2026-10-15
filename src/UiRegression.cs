using System;
using System.IO;
using System.Linq;
using System.Drawing;
using System.Collections.Generic;
using System.Threading.Tasks;
using System.Windows.Forms;
namespace ZapretManager {
public static class UiRegression {
 static IEnumerable<Control> All(Control parent){foreach(Control c in parent.Controls){yield return c;foreach(var child in All(c))yield return child;}}
 public static Task<int> Run(){
  string directory=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"tests");Directory.CreateDirectory(directory);var report=new List<string>();int failures=0;
  Action<bool,string> check=(ok,name)=>{report.Add((ok?"PASS: ":"FAIL: ")+name);if(!ok)failures++;};
  var form=new MainForm();form.Shown+=async(s,e)=>{try{
   check(form.Text=="zaper 3.8.0","short zaper window title");
   check(!All(form).OfType<Button>().Any(b=>b.Text.Contains("Настроить FACEIT")||b.Text=="График задержки"),"no duplicate FACEIT shortcut or separate graph launcher");
   check(All(form).OfType<LatencyPanel>().Count()==1,"graph embedded directly in diagnostics");
   check(await form.NetworkGraph.TestLocal(),"embedded diagnostics graph plots real loopback samples");
   check(!All(form).OfType<Button>().Any(b=>b.Text.Contains("Обновить Hosts"))&&All(form).OfType<Button>().Any(b=>b.Text=="Hosts"),"Hosts editor entry replaces misleading update button");
   using(var servers=new FaceForm()){var buttons=All(servers).OfType<Button>().ToArray();check(buttons.Length==1&&buttons[0].Text=="Проверить","server window has only the requested check action");}
   using(var preferences=new PreferencesForm(()=>{})){check(!All(preferences).OfType<Label>().Any(l=>l.Text.Contains("Крестик")),"tray settings omit redundant close hint");check(All(preferences).OfType<CheckBox>().Count()==3,"tray options retained with descriptions");}
   check(typeof(MainForm).GetMethod("Confirm")==null,"manual Discord confirmation removed");
   using(var graph=new LatencyForm()){bool passed=await graph.TestLocal();File.WriteAllText(Path.Combine(directory,"graph-test.txt"),(passed?"PASS":"FAIL")+": loopback ping samples plotted, counter updates, graph disposal");check(passed,"live graph loopback samples");}
   string root=Core.Root;string fixture=Path.Combine(directory,"startup-fixture");Directory.CreateDirectory(fixture);
   try{Core.Root=fixture;Core.Write(Core.PathOf("ui-preferences.json"),new UiPreferences {StartInTray=true});Program.TestStartupPreferences=true;using(var hidden=new MainForm()){hidden.Show();Application.DoEvents();check(hidden.StartedHidden,"saved StartInTray preference suppresses initial window");check(hidden.TestTray(),"initially hidden window restores and closes to tray");hidden.ExitApp();}Program.TestStartupPreferences=false;}finally{Core.Root=root;Program.TestStartupPreferences=false;}
   bool tray=form.TestTray();File.WriteAllText(Path.Combine(directory,"tray-test.txt"),(tray?"PASS":"FAIL")+": status/menu states, operation lock, minimize/cross hide and restore");check(tray,"tray lifecycle");
   Tests.Preview(form);Tests.PreviewExclusions();check(File.ReadAllText(Path.Combine(directory,"layout-test.txt")).Contains("Failures: 0"),"all pages fit default and minimum sizes");
  }catch(Exception ex){check(false,ex.ToString());}finally{form.ExitApp();check(form.IsDisposed&&form.TrayReleased,"explicit exit closes form and removes tray icon");File.AppendAllText(Path.Combine(directory,"tray-test.txt"),Environment.NewLine+(form.IsDisposed&&form.TrayReleased?"PASS":"FAIL")+": explicit exit closes form and removes tray icon");report.Add("Failures: "+failures);File.WriteAllLines(Path.Combine(directory,"ui-test.txt"),report);}};
  Application.Run(form);return Task.FromResult(failures==0?0:1);
 }
}
}
