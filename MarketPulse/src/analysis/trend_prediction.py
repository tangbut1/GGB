import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple
from pathlib import Path
import json
from datetime import datetime, timedelta
from prophet import Prophet
import warnings
warnings.filterwarnings('ignore')


class TrendPredictor:
    """趋势预测器 - 基于Prophet模型的市场趋势预测"""
    
    def __init__(self):
        self.model = None
        self.forecast_periods = 30  # 默认预测30天
        
    def prepare_data(self, sentiment_data: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        准备预测数据
        
        Args:
            sentiment_data: 情绪分析数据
            
        Returns:
            格式化的时间序列数据
        """
        if not sentiment_data:
            return pd.DataFrame()
        
        # 提取时间和情绪得分
        data_points = []
        for news in sentiment_data:
            # 使用发布时间或当前时间
            publish_time = news.get('publish_time', datetime.now().strftime('%Y-%m-%d'))
            sentiment_score = news.get('sentiment_score', 0)
            
            # 转换时间格式
            try:
                if isinstance(publish_time, str):
                    date_obj = datetime.strptime(publish_time[:10], '%Y-%m-%d')
                else:
                    date_obj = publish_time
            except:
                date_obj = datetime.now()
            
            data_points.append({
                'ds': date_obj,
                'y': sentiment_score
            })
        
        df = pd.DataFrame(data_points)
        
        # 按日期聚合，计算每日平均情绪
        if not df.empty:
            df = df.groupby('ds')['y'].mean().reset_index()
            df['ds'] = pd.to_datetime(df['ds'])
        
        return df
    
    def train_model(self, df: pd.DataFrame) -> bool:
        """
        训练Prophet模型
        
        Args:
            df: 时间序列数据
            
        Returns:
            是否训练成功
        """
        if df.empty or len(df) < 7:  # 至少需要7天数据
            return False
        
        try:
            # 创建Prophet模型
            self.model = Prophet(
                daily_seasonality=True,
                weekly_seasonality=True,
                yearly_seasonality=False,
                changepoint_prior_scale=0.05,
                seasonality_prior_scale=10.0
            )
            
            # 训练模型
            self.model.fit(df)
            return True
        except Exception as e:
            print(f"模型训练失败: {e}")
            return False
    
    def predict_trend(self, periods: int = None) -> Dict[str, Any]:
        """
        预测未来趋势
        
        Args:
            periods: 预测天数
            
        Returns:
            预测结果
        """
        if not self.model:
            return {'error': '模型未训练'}
        
        periods = periods or self.forecast_periods
        
        try:
            # 创建未来日期
            future = self.model.make_future_dataframe(periods=periods)
            
            # 进行预测
            forecast = self.model.predict(future)
            
            # 提取预测结果
            predictions = forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(periods)
            
            # 计算趋势方向
            recent_trend = self._calculate_trend_direction(forecast)
            
            return {
                'predictions': predictions.to_dict('records'),
                'trend_direction': recent_trend,
                'confidence': self._calculate_confidence(forecast),
                'forecast_periods': periods
            }
        except Exception as e:
            return {'error': f'预测失败: {e}'}
    
    def _calculate_trend_direction(self, forecast: pd.DataFrame) -> str:
        """计算趋势方向"""
        if len(forecast) < 2:
            return 'neutral'
        
        # 比较最后几天的预测值
        recent_values = forecast['yhat'].tail(7).values
        if len(recent_values) < 2:
            return 'neutral'
        
        # 计算斜率
        x = np.arange(len(recent_values))
        slope = np.polyfit(x, recent_values, 1)[0]
        
        if slope > 0.01:
            return 'positive'
        elif slope < -0.01:
            return 'negative'
        else:
            return 'neutral'
    
    def _calculate_confidence(self, forecast: pd.DataFrame) -> float:
        """计算预测置信度"""
        if len(forecast) < 2:
            return 0.0
        
        # 基于预测区间的宽度计算置信度
        recent_forecast = forecast.tail(7)
        avg_uncertainty = (recent_forecast['yhat_upper'] - recent_forecast['yhat_lower']).mean()
        
        # 转换为0-1的置信度分数
        confidence = max(0.0, min(1.0, 1.0 - avg_uncertainty / 2.0))
        return round(confidence, 3)
    
    def analyze_market_sentiment_trend(self, sentiment_data: List[Dict[str, Any]], 
                                     periods: int = 30) -> Dict[str, Any]:
        """
        分析市场情绪趋势
        
        Args:
            sentiment_data: 情绪分析数据
            periods: 预测天数
            
        Returns:
            完整的趋势分析结果
        """
        # 准备数据
        df = self.prepare_data(sentiment_data)
        
        if df.empty:
            return {
                'error': '数据不足，无法进行趋势预测',
                'data_points': 0
            }
        
        # 训练模型
        if not self.train_model(df):
            return {
                'error': '模型训练失败',
                'data_points': len(df)
            }
        
        # 进行预测
        prediction_result = self.predict_trend(periods)
        
        if 'error' in prediction_result:
            return prediction_result
        
        # 生成分析摘要
        analysis_summary = {
            'data_points': len(df),
            'forecast_periods': periods,
            'trend_direction': prediction_result['trend_direction'],
            'confidence': prediction_result['confidence'],
            'predictions': prediction_result['predictions'],
            'historical_data': df.to_dict('records')
        }
        
        return analysis_summary
    
    def save_prediction_results(self, results: Dict[str, Any], 
                              file_path: str = "results/logs/trend_prediction.json"):
        """
        保存预测结果
        
        Args:
            results: 预测结果
            file_path: 保存路径
        """
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        # 添加时间戳
        results['generated_at'] = datetime.now().isoformat()
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"✅ 趋势预测结果已保存到 {file_path}")
    
    def get_trend_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取趋势摘要
        
        Args:
            results: 预测结果
            
        Returns:
            趋势摘要
        """
        if 'error' in results:
            return {
                'status': 'error',
                'message': results['error']
            }
        
        trend_direction = results.get('trend_direction', 'neutral')
        confidence = results.get('confidence', 0.0)
        
        # 根据趋势方向生成建议
        if trend_direction == 'positive':
            recommendation = "市场情绪呈积极趋势，建议关注相关投资机会"
        elif trend_direction == 'negative':
            recommendation = "市场情绪呈消极趋势，建议谨慎投资"
        else:
            recommendation = "市场情绪相对稳定，建议保持观望"
        
        return {
            'status': 'success',
            'trend_direction': trend_direction,
            'confidence': confidence,
            'recommendation': recommendation,
            'data_points': results.get('data_points', 0),
            'forecast_periods': results.get('forecast_periods', 0)
        }


def predict_market_trend(sentiment_data: List[Dict[str, Any]], periods: int = 30) -> Dict[str, Any]:
    """
    便捷函数：预测市场趋势
    
    Args:
        sentiment_data: 情绪分析数据
        periods: 预测天数
        
    Returns:
        预测结果
    """
    predictor = TrendPredictor()
    return predictor.analyze_market_sentiment_trend(sentiment_data, periods)
