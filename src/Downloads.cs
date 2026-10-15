using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Net;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
namespace ZapretManager {
public static class Downloads {
 public static async Task<string> Fetch(string url,CancellationToken token){
  using(var stop=CancellationTokenSource.CreateLinkedTokenSource(token)){
   var modes=new List<string>{null};string proxy=Core.Proxy();
   if(!string.IsNullOrWhiteSpace(proxy)){if(proxy.Contains("=")){var match=System.Text.RegularExpressions.Regex.Match(proxy,@"(?:^|;)https?=([^;]+)");proxy=match.Success?match.Groups[1].Value:"";}if(proxy!="")modes.Add(proxy);}
   var pending=modes.Select(p=>FetchRoute(url,p,stop.Token)).ToList();var errors=new List<Exception>();
   try{while(pending.Count>0){token.ThrowIfCancellationRequested();var done=await Task.WhenAny(pending);pending.Remove(done);try{return await done;}catch(OperationCanceledException){token.ThrowIfCancellationRequested();}catch(Exception e){errors.Add(e);}}throw new IOException("Не удалось загрузить данные напрямую и через доступный proxy. Текущие файлы сохранены.",errors.LastOrDefault());}
   finally{stop.Cancel();foreach(var job in pending)try{job.GetAwaiter().GetResult();}catch{}}
  }
 }
 static async Task<string> FetchRoute(string url,string proxy,CancellationToken token){
  var args=(proxy==null?"--noproxy \"*\"":"--noproxy \"\" --proxy "+Core.Quote(proxy.Contains("://")?proxy:"http://"+proxy))+" --fail --location --compressed --silent --show-error --connect-timeout 5 --max-time 18 --max-filesize 4194304 --user-agent zaper/3.8.0 "+Core.Quote(url);
  var result=await Core.Run(Path.Combine(Environment.SystemDirectory,"curl.exe"),args,token,21000);
  if(result.Exit!=0||string.IsNullOrWhiteSpace(result.Output))throw new IOException("Источник недоступен: "+new Uri(url).Host+" (curl "+result.Exit+")");return result.Output;
 }
 public static async Task<string> IPSet(CancellationToken token){
  var sources=new[]{"https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/main/.service/ipset-service.txt","https://api.github.com/repos/Flowseal/zapret-discord-youtube/contents/.service/ipset-service.txt"};
  foreach(var source in sources){try{string text=await Fetch(source,token);if(source.Contains("api.github.com")){var data=Core.Json.Deserialize<Dictionary<string,object>>(text);text=Encoding.UTF8.GetString(Convert.FromBase64String(Convert.ToString(data["content"])));}Core.ValidateIPSet(text);return text;}catch(OperationCanceledException){throw;}catch{}}
  throw new IOException("IP-список недоступен на обоих официальных адресах. Проверьте соединение и повторите позже. Прежний список не изменён.");
 }
}
}
