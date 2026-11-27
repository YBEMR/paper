// Exact layered shortest path for one fixed device sequence. The state key is (finish, OPP).
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <utility>
#include <vector>
using std::vector;
using Choice = std::pair<double,int>;
static constexpr double INF=std::numeric_limits<double>::infinity();

extern "C" double frequency_dp(int n,int m,int horizon,int last_epoch,double sw,
  const int* ready,const int* limit,const int* decision,const int* duration,
  const double* active,const double* rate,const double* active_beta,const double* idle_beta,
  const double* temp,int compact,int* path,int64_t* stats,double* debug,int debug_width) {
  vector<double> prev(m,INF); prev[0]=0;
  vector<vector<int>> parents(n);
  vector<int> origins(n);
  int lower=0, upper=0;
  // The frozen causal idle decision always uses reference power, also in thermal mode.
  auto gap=[&](int t,int s,int a,int b,int epoch){
    bool change=a!=b;
    double hold=rate[a]*(s-t)+sw*change, drop=rate[a]*5+sw*(1+(b!=0));
    bool early=a>0 && t>=epoch && s-t>=5*(1+(b!=0)) && drop<hold;
    double answer=early?drop:hold;
    int end=early?t+5:s;
    if(idle_beta[a]!=0) answer+=idle_beta[a]*(temp[end]-temp[t]);
    return answer;
  };
  for(int i=0;i<n;i++){
    int lo=ready[i]+*std::min_element(duration+i*m,duration+(i+1)*m), hi=std::min(horizon,limit[i]);
    if(lo>hi)return INF;
    origins[i]=lo;
    vector<double> next((hi-lo+1)*m,INF);
    vector<int>& back=parents[i];back.assign(next.size(),-1);
    auto offer=[&](int s,int b,Choice entry){
      if(!std::isfinite(entry.first))return;
      int z=s+duration[i*m+b]; if(z>hi)return;
      double cost=entry.first+active[i*m+b]+active_beta[i*m+b]*(temp[z]-temp[s]);
      int j=(z-lo)*m+b;
      if(cost<next[j] || (cost==next[j] && entry.second<back[j])){
        next[j]=cost;back[j]=entry.second;
      }
    };
    for(int t=lower;t<=upper;t++){
      const int stay=std::max(t,ready[i]), change=std::max(t+5,ready[i]);
      Choice first={INF,-1},second=first,zero=first;
      for(int a=0;a<m;a++){
        double v=prev[(t-lower)*m+a]; if(!std::isfinite(v))continue;
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
    for(size_t j=0;j<next.size();j++)if(std::isfinite(next[j])){
      stats[i*3+2]++;
      if(debug_width)debug[(i*debug_width+lo+int(j)/m)*m+j%m]=next[j];
    }
    if(!stats[i*3+2])return INF;
    prev.swap(next);lower=lo;upper=hi;
  }
  Choice best={INF,-1};
  for(int t=lower;t<=upper;t++)for(int a=0;a<m;a++){
    double v=prev[(t-lower)*m+a];
    if(t+5*(a!=0)<=horizon && std::isfinite(v))
      best=std::min(best,Choice{v+gap(t,horizon,a,0,last_epoch),t*m+a});
  }
  if(!std::isfinite(best.first))return INF;
  int key=best.second;
  for(int i=n-1;i>=0;i--){
    path[i]=key%m;key=parents[i][key-origins[i]*m];
  }
  return best.first;
}
