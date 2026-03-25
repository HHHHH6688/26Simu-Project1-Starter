import math

class UniswapV3Simulator:
    def __init__(self, initial_price: float, initial_liquidity: int):
        # 计算 sqrtPriceX96 = sqrt(P) * 2^96（使用 Q64.96 定点数）
        sqrtP = math.sqrt(initial_price)
        self.sqrtPriceX96 = int(sqrtP * (2**96))  # Q64.96 定点数
        
        # 计算 current_tick = log_{1.0001}(P)
        self.current_tick = int(math.log(initial_price, 1.0001))
        
        # 初始化 liquidity
        self.liquidity = initial_liquidity
        
        # 初始化 ticks 字典，只包含当前 tick 上下限的流动性信息
        self.ticks = {}
        # 当前 tick 的流动性信息
        self.ticks[self.current_tick] = {
            "liquidity_net": 0,
            "liquidity_gross": 0,
            "fee_growth": 0
        }
        # 上一个 tick 的流动性信息
        self.ticks[self.current_tick - 1] = {
            "liquidity_net": 0,
            "liquidity_gross": 0,
            "fee_growth": 0
        }
        # 下一个 tick 的流动性信息
        self.ticks[self.current_tick + 1] = {
            "liquidity_net": 0,
            "liquidity_gross": 0,
            "fee_growth": 0
        }
        
        # 初始化 feeGrowthGlobal
        self.feeGrowthGlobal = 0
    
    def swap_in_tick(self, is_buy, amount, sqrtPriceX96, liquidity, feeGrowthGlobal):
        """处理同区间内的交易"""
        # 计算手续费（0.3%）
        fee_rate = 0.003
        fee_amount = int(amount * fee_rate)
        amount_after_fee = amount - fee_amount
        
        # 计算当前价格 P = (sqrtPriceX96 / 2^96)^2（使用 Q64.96 定点数）
        sqrtP = sqrtPriceX96 / (2**96)  # 转换为浮点数进行计算
        
        # 根据买入/卖出计算价格移动和用户输出
        if is_buy:
            # 买入：用户支付 ETH，获得 token
            # L = Δx * sqrt(P) → Δx = L / sqrt(P)
            # 但这里用户支付的是 amount_after_fee，所以实际是 Δx = amount_after_fee
            # 因此价格变化为：新的 sqrtP' = sqrtP + (Δx / L)
            if liquidity == 0:
                # 流动性为 0 时无法交易
                return (sqrtPriceX96, liquidity, 0, 0)
            
            # 计算价格变化
            delta_sqrtP = amount_after_fee / liquidity
            new_sqrtP = sqrtP + delta_sqrtP
            new_sqrtPriceX96 = int(new_sqrtP * (2**96))  # 转换回 Q64.96 定点数
            
            # 计算用户获得的 token 数量：Δy = L * (1/sqrtP - 1/new_sqrtP)
            user_output = int(liquidity * (1/sqrtP - 1/new_sqrtP))
        else:
            # 卖出：用户支付 token，获得 ETH
            # L = Δy / sqrt(P) → Δy = L * sqrt(P)
            # 但这里用户支付的是 amount_after_fee，所以实际是 Δy = amount_after_fee
            # 因此价格变化为：新的 sqrtP' = sqrtP - (Δy / L)
            if liquidity == 0:
                # 流动性为 0 时无法交易
                return (sqrtPriceX96, liquidity, 0, 0)
            
            # 计算价格变化
            delta_sqrtP = amount_after_fee / liquidity
            new_sqrtP = sqrtP - delta_sqrtP
            if new_sqrtP < 0:
                # 价格不能为负
                return (sqrtPriceX96, liquidity, 0, 0)
            new_sqrtPriceX96 = int(new_sqrtP * (2**96))  # 转换回 Q64.96 定点数
            
            # 计算用户获得的 ETH 数量：Δx = L * (sqrtP - new_sqrtP)
            user_output = int(liquidity * (sqrtP - new_sqrtP))
        
        # 更新 feeGrowthGlobal
        new_feeGrowthGlobal = feeGrowthGlobal + fee_amount
        
        # 不跨 tick 时直接更新 sqrtPriceX96 和 liquidity
        # 注意：这里假设不跨 tick，所以 current_tick 不变
        
        return (new_sqrtPriceX96, liquidity, user_output, fee_amount)
    
    def swap_cross_ticks(self, is_buy, amount, sqrtPriceX96, current_tick, liquidity, ticks):
        """处理跨 tick 的交易"""
        # 计算手续费（0.3%）
        fee_rate = 0.003
        fee_amount = int(amount * fee_rate)
        amount_after_fee = amount - fee_amount
        
        # 初始化返回值
        new_sqrtPriceX96 = sqrtPriceX96
        new_current_tick = current_tick
        new_liquidity = liquidity
        user_output = 0
        
        # 剩余交易量
        remaining_amount = amount_after_fee
        
        # 循环处理跨 tick 交易
        while remaining_amount > 0:
            # 计算当前 tick 能处理的最大交易量
            # 首先计算当前价格和下一个 tick 的价格
            sqrtP = new_sqrtPriceX96 / (2**96)  # 转换为浮点数进行计算
            
            # 确定下一个 tick 的方向
            if is_buy:
                # 买入：价格上涨，tick 增加
                next_tick = new_current_tick + 1
            else:
                # 卖出：价格下跌，tick 减少
                next_tick = new_current_tick - 1
            
            # 检查下一个 tick 是否存在于 ticks 字典中
            if next_tick not in ticks:
                # 到达价格边界，无法继续交易
                break
            
            # 计算下一个 tick 的价格
            # tick 价格计算公式：P = 1.0001^tick
            next_tick_price = 1.0001 ** next_tick
            next_sqrtP = math.sqrt(next_tick_price)
            next_sqrtPriceX96 = int(next_sqrtP * (2**96))  # 转换为 Q64.96 定点数
            
            # 计算当前 tick 能处理的最大交易量
            if is_buy:
                # 买入：Δx = L * (next_sqrtP - sqrtP)
                max_amount = int(new_liquidity * (next_sqrtP - sqrtP))
            else:
                # 卖出：Δy = L * (sqrtP - next_sqrtP)
                max_amount = int(new_liquidity * (sqrtP - next_sqrtP))
            
            if remaining_amount <= max_amount:
                # 剩余交易量小于等于当前 tick 能处理的最大交易量
                # 计算价格变化
                if is_buy:
                    delta_sqrtP = remaining_amount / new_liquidity
                    new_sqrtP = sqrtP + delta_sqrtP
                    # 计算用户获得的 token 数量：Δy = L * (1/sqrtP - 1/new_sqrtP)
                    user_output += int(new_liquidity * (1/sqrtP - 1/new_sqrtP))
                else:
                    delta_sqrtP = remaining_amount / new_liquidity
                    new_sqrtP = sqrtP - delta_sqrtP
                    # 计算用户获得的 ETH 数量：Δx = L * (sqrtP - new_sqrtP)
                    user_output += int(new_liquidity * (sqrtP - new_sqrtP))
                
                new_sqrtPriceX96 = int(new_sqrtP * (2**96))  # 转换回 Q64.96 定点数
                remaining_amount = 0
            else:
                # 剩余交易量大于当前 tick 能处理的最大交易量
                # 耗尽当前 tick
                if is_buy:
                    # 计算用户获得的 token 数量：Δy = L * (1/sqrtP - 1/next_sqrtP)
                    user_output += int(new_liquidity * (1/sqrtP - 1/next_sqrtP))
                else:
                    # 计算用户获得的 ETH 数量：Δx = L * (sqrtP - next_sqrtP)
                    user_output += int(new_liquidity * (sqrtP - next_sqrtP))
                
                # 切换到下一个 tick
                new_current_tick = next_tick
                new_sqrtPriceX96 = next_sqrtPriceX96
                
                # 从 ticks 字典中注入下一个 tick 的流动性
                # 注意：这里假设 ticks 字典中存储了 liquidity_net
                if "liquidity_net" in ticks[new_current_tick]:
                    new_liquidity += ticks[new_current_tick]["liquidity_net"]
                
                # 减少剩余交易量
                remaining_amount -= max_amount
        
        return (new_sqrtPriceX96, new_current_tick, new_liquidity, user_output, fee_amount)
    
    def swap(self, is_buy: bool, amount: int) -> int:
        """自动判断是否跨 tick，调用 swap_in_tick 或 swap_cross_ticks"""
        # 计算当前 tick 能处理的最大交易量，判断是否跨 tick
        sqrtP = self.sqrtPriceX96 / (2**96)  # 转换为浮点数进行计算
        
        # 确定下一个 tick 的方向
        if is_buy:
            # 买入：价格上涨，tick 增加
            next_tick = self.current_tick + 1
        else:
            # 卖出：价格下跌，tick 减少
            next_tick = self.current_tick - 1
        
        # 检查下一个 tick 是否存在于 ticks 字典中
        if next_tick not in self.ticks:
            # 到达价格边界，无法跨 tick
            result = self.swap_in_tick(is_buy, amount, self.sqrtPriceX96, self.liquidity, self.feeGrowthGlobal)
            new_sqrtPriceX96, new_liquidity, user_output, fee_amount = result
            
            # 更新状态
            self.sqrtPriceX96 = new_sqrtPriceX96
            self.liquidity = new_liquidity
            self.feeGrowthGlobal += fee_amount
            
            return user_output
        
        # 计算下一个 tick 的价格
        next_tick_price = 1.0001 ** next_tick
        next_sqrtP = math.sqrt(next_tick_price)
        
        # 计算当前 tick 能处理的最大交易量
        if is_buy:
            # 买入：Δx = L * (next_sqrtP - sqrtP)
            max_amount = int(self.liquidity * (next_sqrtP - sqrtP))
        else:
            # 卖出：Δy = L * (sqrtP - next_sqrtP)
            max_amount = int(self.liquidity * (sqrtP - next_sqrtP))
        
        # 计算手续费后的金额
        fee_rate = 0.003
        amount_after_fee = amount - int(amount * fee_rate)
        
        if amount_after_fee <= max_amount:
            # 不需要跨 tick，调用 swap_in_tick
            result = self.swap_in_tick(is_buy, amount, self.sqrtPriceX96, self.liquidity, self.feeGrowthGlobal)
            new_sqrtPriceX96, new_liquidity, user_output, fee_amount = result
            
            # 更新状态
            self.sqrtPriceX96 = new_sqrtPriceX96
            self.liquidity = new_liquidity
            self.feeGrowthGlobal += fee_amount
            
            return user_output
        else:
            # 需要跨 tick，调用 swap_cross_ticks
            result = self.swap_cross_ticks(is_buy, amount, self.sqrtPriceX96, self.current_tick, self.liquidity, self.ticks)
            new_sqrtPriceX96, new_current_tick, new_liquidity, user_output, fee_amount = result
            
            # 更新状态
            self.sqrtPriceX96 = new_sqrtPriceX96
            self.current_tick = new_current_tick
            self.liquidity = new_liquidity
            self.feeGrowthGlobal += fee_amount
            
            return user_output
    
    def get_fee_growth(self) -> int:
        """返回累计的手续费"""
        return self.feeGrowthGlobal
