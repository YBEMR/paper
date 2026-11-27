// Exact layered shortest path for one fixed device sequence. The state key is (finish, OPP).
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <utility>
#include <type_traits>
#include <vector>
using std::vector;
using Wide = __int128_t;
constexpr double no_solution=std::numeric_limits<double>::infinity();

template<class Cost> static double search(int n,int m,int horizon,int last_epoch,Cost sw,
  const int* ready,const int* limit,const int* decision,const int* duration,
  const Cost* active,const Cost* rate,const double* active_beta,const double* idle_beta,
  const double* temp,int compact,int* path,int64_t* stats,double* debug,int debug_width) {
  using Choice=std::pair<Cost,int>;
  const Cost INF=std::numeric_limits<Cost>::has_infinity?std::numeric_limits<Cost>::infinity():std::numeric_limits<Cost>::max();
  vector<Cost> prev(m,INF); prev[0]=0;
  vector<vector<int>> parents(n);
  vector<int> origins(n);
  int lower=0, upper=0;
  // The frozen causal idle decision always uses reference power, also in thermal mode.
  auto gap=[&](int t,int s,int a,int b,int epoch){
    bool change=a!=b;
    Cost hold=rate[a]*(s-t)+sw*change, drop=rate[a]*5+sw*(1+(b!=0));
    bool early=a>0 && t>=epoch && s-t>=5*(1+(b!=0)) && drop<hold;
    Cost answer=early?drop:hold;
    int end=early?t+5:s;
    if constexpr(std::is_same_v<Cost,double>) if(idle_beta[a]!=0) answer+=idle_beta[a]*(temp[end]-temp[t]);
    return answer;
  };
  for(int i=0;i<n;i++){
    int lo=ready[i]+*std::min_element(duration+i*m,duration+(i+1)*m), hi=std::min(horizon,limit[i]);
    if(lo>hi)return no_solution;
    origins[i]=lo;
    vector<Cost> next((hi-lo+1)*m,INF);
    vector<int>& back=parents[i];back.assign(next.size(),-1);
    auto offer=[&](int s,int b,Choice entry){
      if(entry.first==INF)return;
      int z=s+duration[i*m+b]; if(z>hi)return;
      Cost cost=entry.first+active[i*m+b];
      if constexpr(std::is_same_v<Cost,double>) cost+=active_beta[i*m+b]*(temp[z]-temp[s]);
      int j=(z-lo)*m+b;
      if(cost<next[j] || (cost==next[j] && entry.second<back[j])){
        next[j]=cost;back[j]=entry.second;
      }
    };
    for(int t=lower;t<=upper;t++){
      const int stay=std::max(t,ready[i]), change=std::max(t+5,ready[i]);
      Choice first={INF,-1},second=first,zero=first;
      for(int a=0;a<m;a++){
        Cost v=prev[(t-lower)*m+a]; if(v==INF)continue;
        stats[i*3]++; int state=t*m+a;
        if(!compact){
          for(int b=0;b<m;b++){
            int s=b==a?stay:change;
            if(s+duration[i*m+b]<=hi)offer(s,b,{v+gap(t,s,a,b,decision[i]),state});
            stats[i*3+1]++;
          }
          continue;
        }
        if(stay+duration[i*m+a]<=hi)offer(stay,a,{v+gap(t,stay,a,a,decision[i]),state});
        stats[i*3+1]++;
        if(change>hi)continue;
        // All changed positive destinations have the same gap cost. Exclude the
        // destination itself using the second-best predecessor when necessary.
        int other_positive=(a==1?2:1);
        Choice ch={v+gap(t,change,a,other_positive,decision[i]),state};
        if(ch<first){second=first;first=ch;}else if(ch<second)second=ch;
        if(a!=0)zero=std::min(zero,Choice{v+gap(t,change,a,0,decision[i]),state});
      }
      if(compact && change<=hi){
        offer(change,0,zero);
        for(int b=1;b<m;b++)offer(change,b,first.second>=0 && first.second%m==b?second:first);
      }
    }
    for(size_t j=0;j<next.size();j++)if(next[j]!=INF){
      stats[i*3+2]++;
      if(debug_width)debug[(i*debug_width+lo+int(j)/m)*m+j%m]=next[j];
    }
    if(!stats[i*3+2])return no_solution;
    prev.swap(next);lower=lo;upper=hi;
  }
  Choice best={INF,-1};
  for(int t=lower;t<=upper;t++)for(int a=0;a<m;a++){
    Cost v=prev[(t-lower)*m+a];
    if(t+5*(a!=0)<=horizon && v!=INF)
      best=std::min(best,Choice{v+gap(t,horizon,a,0,last_epoch),t*m+a});
  }
  if(best.first==INF)return no_solution;
  int key=best.second;
  for(int i=n-1;i>=0;i--){
    path[i]=key%m;key=parents[i][key-origins[i]*m];
  }
  return static_cast<double>(best.first);
}
extern "C" double frequency_dp(int n,int m,int h,int epoch,double sw,const int* ready,const int* limit,
 const int* decision,const int* dt,const double* act,const double* rate,const double* beta,const double* ib,
 const double* T,int compact,int* path,int64_t* stats,double* dbg,int width){
 return search(n,m,h,epoch,sw,ready,limit,decision,dt,act,rate,beta,ib,T,compact,path,stats,dbg,width);
}
extern "C" double exact_dp(int n,int m,int h,int epoch,const uint64_t* words,const int* ready,const int* limit,
 const int* decision,const int* dt,int compact,int* path,int64_t* stats,double* dbg,int width){
 vector<Wide> values(1+m+n*m);
 for(size_t j=0;j<values.size();j++)values[j]=(Wide(words[2*j])<<64)+words[2*j+1];
 return search(n,m,h,epoch,values[0],ready,limit,decision,dt,values.data()+1+m,values.data()+1,
               nullptr,nullptr,nullptr,compact,path,stats,dbg,width);
}
