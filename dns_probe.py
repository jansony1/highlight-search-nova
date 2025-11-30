#!/usr/bin/env python3
"""
DNS 解析探测工具 - 用于探测按比例分配的 DNS 解析结果
绕过本地缓存，直接查询权威 DNS 服务器
"""

import dns.resolver
import dns.query
import dns.message
import time
from collections import Counter
import argparse


class DNSProber:
    """DNS 解析探测器"""

    def __init__(self, domain, dns_servers=None):
        self.domain = domain
        # 使用多个公共 DNS 服务器以获得更多样化的结果
        self.dns_servers = dns_servers or [
            '8.8.8.8',      # Google DNS
            '8.8.4.4',      # Google DNS Secondary
            '1.1.1.1',      # Cloudflare DNS
            '1.0.0.1',      # Cloudflare DNS Secondary
            '208.67.222.222',  # OpenDNS
            '208.67.220.220',  # OpenDNS Secondary
            '9.9.9.9',      # Quad9 DNS
            '149.112.112.112',  # Quad9 Secondary
            '114.114.114.114',  # 114 DNS (China)
            '223.5.5.5',    # Alibaba DNS (China)
            '223.6.6.6',    # Alibaba DNS Secondary
        ]

    def query_dns_direct(self, dns_server, record_type='A'):
        """
        直接查询指定 DNS 服务器，绕过本地缓存

        Args:
            dns_server: DNS 服务器地址
            record_type: 记录类型 (A, CNAME, AAAA 等)
        """
        try:
            # 创建查询消息
            query = dns.message.make_query(self.domain, record_type)

            # 直接向 DNS 服务器发送查询，不使用缓存
            response = dns.query.udp(query, dns_server, timeout=3)

            results = []

            # 解析响应
            for rrset in response.answer:
                for rr in rrset:
                    if record_type == 'CNAME':
                        results.append(str(rr.target).rstrip('.'))
                    elif record_type == 'A':
                        results.append(str(rr))
                    elif record_type == 'AAAA':
                        results.append(str(rr))

            return results

        except Exception as e:
            # print(f"查询失败 [{dns_server}]: {e}")
            return []

    def probe_multiple_times(self, count=100, record_type='CNAME', delay=0.1):
        """
        多次探测 DNS 解析结果

        Args:
            count: 探测次数
            record_type: 记录类型
            delay: 每次查询之间的延迟（秒）
        """
        results = []

        print(f"🔍 开始探测 {self.domain} 的 {record_type} 记录")
        print(f"📊 探测次数: {count}")
        print(f"🌐 使用 {len(self.dns_servers)} 个 DNS 服务器")
        print("-" * 60)

        for i in range(count):
            # 轮询使用不同的 DNS 服务器
            dns_server = self.dns_servers[i % len(self.dns_servers)]

            result = self.query_dns_direct(dns_server, record_type)

            if result:
                results.extend(result)
                print(f"[{i+1:3d}/{count}] DNS: {dns_server:15s} -> {', '.join(result)}")
            else:
                print(f"[{i+1:3d}/{count}] DNS: {dns_server:15s} -> (无结果)")

            # 添加延迟避免被限流
            if delay > 0 and i < count - 1:
                time.sleep(delay)

        return results

    def analyze_results(self, results):
        """分析解析结果"""
        if not results:
            print("\n❌ 没有获取到任何解析结果")
            return

        print("\n" + "=" * 60)
        print("📈 解析结果统计")
        print("=" * 60)

        counter = Counter(results)
        total = len(results)

        print(f"\n总解析次数: {total}")
        print(f"不同结果数: {len(counter)}")
        print("\n各结果分布:")

        for result, count in counter.most_common():
            percentage = (count / total) * 100
            bar = '█' * int(percentage / 2)
            print(f"  {result:50s} | {count:4d} 次 ({percentage:5.1f}%) {bar}")

        print("\n" + "=" * 60)

    def resolve_cname_chain(self, dns_server='8.8.8.8'):
        """
        解析完整的 CNAME 链
        """
        print(f"\n🔗 解析 {self.domain} 的完整 CNAME 链")
        print("-" * 60)

        current = self.domain
        chain = [current]

        while True:
            cnames = self.query_dns_direct(dns_server, 'CNAME')

            if not cnames:
                # 没有更多 CNAME，尝试获取 A 记录
                a_records = self.query_dns_direct(dns_server, 'A')
                if a_records:
                    print(f"{current} -> A: {', '.join(a_records)}")
                break

            cname = cnames[0]
            print(f"{current} -> CNAME: {cname}")
            chain.append(cname)
            current = cname

            # 防止无限循环
            if len(chain) > 10:
                print("⚠️  CNAME 链过长，可能存在循环")
                break

        return chain


def main():
    parser = argparse.ArgumentParser(
        description='DNS 解析探测工具 - 探测按比例分配的 DNS 结果',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 探测 100 次 CNAME 记录
  python dns_probe.py chat.deepseek.com -n 100

  # 探测 200 次，使用 A 记录
  python dns_probe.py chat.deepseek.com -n 200 -t A

  # 查看 CNAME 链
  python dns_probe.py chat.deepseek.com --chain

  # 使用自定义 DNS 服务器
  python dns_probe.py chat.deepseek.com -n 100 -d 8.8.8.8 1.1.1.1

  # 增加延迟避免限流
  python dns_probe.py chat.deepseek.com -n 100 --delay 0.2
        """
    )

    parser.add_argument('domain', help='要探测的域名')
    parser.add_argument('-n', '--count', type=int, default=100,
                      help='探测次数 (默认: 100)')
    parser.add_argument('-t', '--type', default='CNAME',
                      choices=['A', 'CNAME', 'AAAA'],
                      help='DNS 记录类型 (默认: CNAME)')
    parser.add_argument('-d', '--dns-servers', nargs='+',
                      help='自定义 DNS 服务器列表')
    parser.add_argument('--delay', type=float, default=0.05,
                      help='每次查询之间的延迟秒数 (默认: 0.05)')
    parser.add_argument('--chain', action='store_true',
                      help='解析完整的 CNAME 链')

    args = parser.parse_args()

    # 创建探测器
    prober = DNSProber(args.domain, args.dns_servers)

    # 如果只是查看 CNAME 链
    if args.chain:
        prober.resolve_cname_chain()
        return

    # 执行探测
    results = prober.probe_multiple_times(
        count=args.count,
        record_type=args.type,
        delay=args.delay
    )

    # 分析结果
    prober.analyze_results(results)


if __name__ == '__main__':
    main()
