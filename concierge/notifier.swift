// GBH Concierge notifier — posts a banner as com.gbh.concierge so macOS shows
// this bundle's AppIcon. Usage: GBHConcierge -title T -message M [-subtitle S] [-sound N]
// Exit: 0 delivered, 2 notifications not allowed, 1 other failure.
import Foundation
import UserNotifications

var args: [String: String] = [:]
var it = CommandLine.arguments.dropFirst().makeIterator()
while let k = it.next() {
    if k.hasPrefix("-"), let v = it.next() { args[String(k.dropFirst())] = v }
}
guard let message = args["message"] else { exit(1) }

let center = UNUserNotificationCenter.current()
let done = DispatchSemaphore(value: 0)
var code: Int32 = 1

center.requestAuthorization(options: [.alert, .sound]) { granted, _ in
    guard granted else { code = 2; done.signal(); return }
    let c = UNMutableNotificationContent()
    c.title = args["title"] ?? "GBH"
    c.body = message
    if let s = args["subtitle"] { c.subtitle = s }
    if let s = args["sound"], s != "default" {
        c.sound = UNNotificationSound(named: UNNotificationSoundName(s))
    } else {
        c.sound = .default
    }
    let req = UNNotificationRequest(identifier: UUID().uuidString, content: c, trigger: nil)
    center.add(req) { err in
        code = err == nil ? 0 : 1
        done.signal()
    }
}
_ = done.wait(timeout: .now() + 8)
exit(code)
